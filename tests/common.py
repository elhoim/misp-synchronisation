#!/usr/bin/env python3
import os
import uuid
import re
from typing import Union
from pymisp import PyMISP, MISPEvent, ThreatLevel, Analysis, MISPAttribute
from pymisp.api import get_uuid_or_id_from_abstract_misp




# Dynamically get HOST and AUTH variables from environment
hosts = []
auths_site_admin = []
auths_org_admin = []
i = 1
while True:
    host_key = f"HOST_{i}"
    auth_site_key = f"AUTH_ADMIN_{i}"
    auth_org_key = f"AUTH_ORG_{i}"
    if host_key in os.environ and auth_site_key in os.environ and auth_org_key in os.environ:
        hosts.append("http://" + os.environ[host_key])
        auths_site_admin.append(os.environ[auth_site_key])
        auths_org_admin.append(os.environ[auth_org_key])
        i += 1
    else:
        break

# Create PyMISP connectors for each host/auth pair
misps_site_admin = [PyMISP(host, auth, ssl=False) for host, auth in zip(hosts, auths_site_admin)]
misps_org_admin = [PyMISP(host, auth, ssl=False) for host, auth in zip(hosts, auths_org_admin)]
print(f"Found {len(misps_site_admin)} MISP instances.")



def create_event(name: str):
    """
    Create a new MISPEvent with a unique UUID, info field, and default attributes.
    Distribution is set to 'Your organisation' (id 0), threat level is 'low', analysis is 'completed'.
    Adds a text attribute containing the event UUID.
    """
    event = MISPEvent()
    event_uuid = str(uuid.uuid4())
    event.info = name
    event.uuid = event_uuid
    event.distribution = 0  # Set distribution to 'Your organisation' (id 0)
    event.threat_level_id = ThreatLevel.low
    event.analysis = Analysis.completed
    event.add_attribute('text', event_uuid)
    return event


def create_attribute(category: str, value: str):
    """
    Create a new MISPAttribute with a unique UUID, category, and value.
    """
    attribute = MISPAttribute()
    attribute_uuid = str(uuid.uuid4())
    attribute.category = category
    attribute.value = value
    attribute.uuid = attribute_uuid
    return attribute

def extract_server_numbers(servers):
    """
    Extract server numbers from the server names.
    Assumes server names are in the format ending with a number (e.g., 'MISP Server X').
    Returns a list of integers.
    """
    numbers = []
    for server in servers:
        name = server['Server']['name']
        match = re.search(r'\d+$', name)
        if match:
            numbers.append(int(match.group()))
    return numbers

def get_servers_id(servers):
    """
    Extract server IDs from the server list.
    Returns a list of IDs.
    """
    ids = []
    for server in servers:
        ids.append(server['Server']['id'])
    return ids

def find_unidirectional_link():
    """
    Find a source/target pair for a unidirectional link.
    Returns (source_instance, target_instance, source_index, target_index, server_id).
    Skips bidirectional links.
    """
    for i, source_instance in enumerate(misps_org_admin):
        source_index = i + 1
        # Extract server numbers from the source instance
        source_links = extract_server_numbers(misps_site_admin[i].servers())

        for target_index in source_links:
            target_instance = misps_org_admin[target_index - 1]
            target_links = extract_server_numbers(misps_site_admin[target_index - 1].servers())

            # Skip bidirectionnel
            if source_index in target_links:
                continue

            # Si la cible ne pointe pas vers la source → sens normal
            # NOTE: the condition below is degenerate on both sides, and that is
            # deliberate -- do not "simplify" it into an inversion.
            #   * `source_index in source_links` asks whether this instance lists
            #     ITSELF as a peer. INSTALL.sh only ever adds servers named
            #     "MISP_<peer>" from topology.conf, which contains no self-entries,
            #     so this is ALWAYS False.
            #   * `source_index not in target_links` is ALWAYS True here, because
            #     bidirectional links were already skipped just above.
            # The else branch therefore ALWAYS fires: the swap is unconditional in
            # practice. That is what makes the result correct -- after the swap the
            # instance that actually holds the server config (the original source)
            # becomes the pull executor, which matches MISP pull semantics.
            # WARNING: do NOT rewrite this as `target_index in source_links`. That
            # is always True (target_index is drawn from source_links), it would
            # suppress the swap, and the server lookup below would then fail for
            # every unidirectional link.
            if source_index in source_links and source_index not in target_links:
                pass
            else:
                # Sens inverse
                source_instance, target_instance = target_instance, source_instance
                source_index, target_index = target_index, source_index

            # Trouver l'ID du serveur sur la cible qui pointe vers la source
            server_id = None
            for server in misps_site_admin[target_index - 1].servers():
                if str(source_index) in server['Server']['name']:
                    server_id = server['Server']['id']
                    break

            if server_id is None:
                continue

            return source_instance, target_instance, source_index, target_index, server_id

    raise Exception("No unidirectional connection found between any instances.")

def purge_events_and_blocklists(instance):
    """
    Delete all events and all event blocklists from a given MISP instance.
    """
    # Delete all events
    for event in instance.search():
        #print(f"Deleting Event {event['Event']['id']} on instance {instance.root_url}")
        instance.delete_event(event['Event']['id'])

    # Delete all event blocklists
    blocklists = instance.event_blocklists()
    for block in blocklists:
        #print(block)
        block_id = block['id']
        #print(f"Deleting EventBlocklist {block_id} on instance {instance.root_url}")
        instance.delete_event_blocklist(block_id)
    print(f"Purged all events and blocklists on instance {instance.root_url}")


def check_response(response):
    """
    Raise an exception if the response contains errors, otherwise return the response.
    """
    if isinstance(response, dict) and "errors" in response:
        raise Exception(response["errors"])
    return response


def request(pymisp: PyMISP, request_type: str, url: str, data: dict = {}) -> dict:
    """
    Send a raw request to the MISP API using PyMISP internals.
    Returns the checked response.
    """
    response = pymisp._prepare_request(request_type, url, data)
    return pymisp._check_response(response)


def publish_immediately(pymisp: PyMISP, event: Union[MISPEvent, int, str, uuid.UUID], with_email: bool = False):
    """
    Publish an event immediately on the given MISP instance.
    If with_email is True, triggers alerting; otherwise, only publishes.
    Disables background processing for faster propagation.
    """
    event_id = get_uuid_or_id_from_abstract_misp(event)
    action = "alert" if with_email else "publish"
    return check_response(request(pymisp, 'POST', f'events/{action}/{event_id}/disable_background_processing:1'))

def unpublish_immediately(pymisp: PyMISP, event: Union[MISPEvent, int, str, uuid.UUID]):
    """
    Unpublish an event immediately on the given MISP instance.
    Disables background processing for faster propagation.
    """
    event_id = get_uuid_or_id_from_abstract_misp(event)
    return check_response(request(pymisp, 'POST', f'events/unpublish/{event_id}/disable_background_processing:1'))
