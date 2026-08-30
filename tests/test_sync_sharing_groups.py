import unittest
import time
from common import misps_site_admin, misps_org_admin, create_event, publish_immediately, check_response, get_servers_id, extract_server_numbers, find_unidirectional_link, purge_events_and_blocklists

class TestSyncSharingGroups(unittest.TestCase):
    def testSharingGroupsOnPush(self):
        """
        Creates an event on the first instance with distribution set to 'Sharing Group',
        associates it with a sharing group shared only with the second organization.
        After publishing and pushing, the event must be present on the first instance
        (its creator) and on the second one (the organisation the sharing group is
        scoped to), and absent from all the other instances.
        """

        source_instance = misps_org_admin[0]
        target_instance = misps_org_admin[1]
        # All other instances except the first two
        other_instances = misps_org_admin[2:] if len(misps_org_admin) > 2 else []

        # Retrieve the already existing sharing group on the first instance
        sharing_groups = source_instance.sharing_groups(pythonify=True)
        if not sharing_groups:
            self.skipTest("No sharing group found on the first instance.")
        # Select the first sharing group for the test
        sg = sharing_groups[0]
        self.assertIsNotNone(sg.id)

        # Create an event with distribution set to 'Sharing Group'
        event = create_event("Event sharing group sync")
        event.distribution = 4  # 4 = Sharing Group
        event.sharing_group_id = sg.id

        event = source_instance.add_event(event, pythonify=True)
        check_response(event)
        self.assertIsNotNone(event.id)
        uuid_event = event.uuid

        # Publish the event
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)

        # Push to all linked servers (to force synchronization)
        servers = misps_site_admin[0].servers()
        servers_id = get_servers_id(servers)
        for server_id in servers_id:
            push_response = misps_site_admin[0].server_push(server=server_id, event=event.id)
            time.sleep(2)
            check_response(push_response)

        # The event must be present on the first server (the one that created it)
        results_source = misps_site_admin[0].search(uuid=uuid_event)
        self.assertGreater(len(results_source), 0, "The event is not present on the first server while it should be.")

        # The event must have been synchronised to the second instance, whose
        # organisation is a member of the sharing group
        results_target = target_instance.search(uuid=uuid_event)
        self.assertGreater(len(results_target), 0, "The event is not present on the second server while the sharing group is shared with its organisation.")

        # The event must NOT be present on the other instances
        for idx, instance in enumerate(other_instances, start=3):
            results = instance.search(uuid=uuid_event)
            self.assertEqual(len(results), 0, f"The event should not be present on server {idx}.")

        # Cleanup: delete all test events on all instances
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)
