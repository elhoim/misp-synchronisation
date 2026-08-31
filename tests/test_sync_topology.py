import unittest
import time
from common import misps_site_admin, misps_org_admin, create_event, publish_immediately, check_response, get_servers_id, extract_server_numbers, purge_events_and_blocklists




class TestSyncForAllServers(unittest.TestCase):
    def testPushForAllServers(self):
        """
        Verifies that events pushed from each MISP instance are correctly propagated to all linked servers.
        Assumes all MISP instances are set up and running.
        Checks that events appear only on the source and its linked servers, not on others.
        Cleans up all test events after execution.
        """
        internal_instances = misps_org_admin[-2:]  # The two internal MISP instances
        for i, source_instance in enumerate(misps_org_admin):
            # Get the list of servers configured on this instance
            linked_servers = extract_server_numbers(misps_site_admin[i].servers())

            # Create a new event with unique info
            event = create_event(f'Push Test Event {misps_org_admin.index(source_instance) + 1}')
            event.distribution = 2  # Connected Community


            # Add the event to the source instance
            event = source_instance.add_event(event, pythonify=True)
            check_response(event)
            self.assertIsNotNone(event.id)
            uuid = event.uuid

            # Publish immediately to trigger push sync
            publish_immediately(source_instance, event, with_email=False)
            time.sleep(2)  # Give time for sync propagation

            # Verify event presence on expected instances
            for target_instance in misps_org_admin:
                target_index = misps_org_admin.index(target_instance) + 1
                found_events = target_instance.search(uuid=uuid)
                if target_instance == source_instance or target_index in linked_servers:
                    # Should exist on source and linked servers
                    self.assertGreater(len(found_events), 0,
                        f"Event not found on MISP {target_index} but should be present.")
                else:
                    if target_instance not in internal_instances:
                        # Should NOT exist on non-linked servers
                        self.assertEqual(len(found_events), 0,
                            f"Event found on MISP {target_index} but should NOT be present.")

        # Cleanup: delete all test events on all instances
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)

    def testPullForAllServers(self):
        """
        Verifies that events can be pulled from a source MISP instance to a target instance via unidirectional sync.
        Skips bidirectional sync links.
        For each unidirectional link, creates and publishes an event on the source, then pulls it on the target.
        Confirms the event appears on the target after the pull.
        Cleans up all test events after execution.
        """
        for i, source_instance in enumerate(misps_org_admin):
            source_index = i + 1
            source_links = extract_server_numbers(misps_site_admin[i].servers())

            for j, target_index in enumerate(source_links):
                # Get the target instance based on the index
                target_instance = misps_org_admin[target_index - 1]
                target_links = extract_server_numbers(misps_site_admin[target_index - 1].servers())

                # Skip bidirectional sync to keep this test unidirectional only
                if source_index in target_links:
                    print(f"Skipping bidirectional sync: {source_index} <--> {target_index}")
                    continue

                print(f"Unidirectional link: {source_index} --> {target_index}")

                # Determine correct source and target depending on link direction
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
                    # Normal direction
                    pass
                else:
                    # Inverse direction
                    source_instance, target_instance = target_instance, source_instance
                    source_index, target_index = target_index, source_index
                    print(f"Inverted direction: {source_index} --> {target_index}")

                # Find the server ID on the target that links to the source
                target_servers = misps_site_admin[target_index - 1].servers()
                server_id = None
                for server in target_servers:
                    name = server['Server']['name']
                    if str(source_index) in name:
                        server_id = server['Server']['id']
                        break

                if server_id is None:
                    raise Exception(f"No server config on MISP_{target_index} pointing to MISP_{source_index}")

                print(f"Pulling from MISP_{source_index} on MISP_{target_index}")

                # Create and publish an event on the source
                event_name = f"Event {source_index} for pull on {target_index}"
                event = create_event(event_name)
                event.distribution = 2

                event = source_instance.add_event(event, pythonify=True)
                check_response(event)
                self.assertIsNotNone(event.id)
                uuid = event.uuid

                publish_immediately(source_instance, event)
                time.sleep(2)  # Give time for publish propagation

                # Perform the pull on the target
                pull_result = misps_site_admin[target_index - 1].server_pull(server=server_id, event=event.id)
                time.sleep(10)  # Allow time for pull to complete
                check_response(pull_result)

                # Confirm the event exists on the target
                found = False
                results = target_instance.search(uuid=uuid)
                if results:
                    found = True
                    break

                self.assertTrue(found, f"Event not found on MISP_{target_index} after pull")

        # Cleanup: delete all test events on all instances
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)