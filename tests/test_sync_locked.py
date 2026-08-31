import unittest
import time
from common import misps_site_admin, misps_org_admin, create_event, publish_immediately, check_response, get_servers_id, extract_server_numbers, find_unidirectional_link, purge_events_and_blocklists

class TestLockedStatus(unittest.TestCase):
    def testLockedStatusOnPush(self):
        """
        Verifies that the 'locked' attribute of an event is correctly set to True when the event is pushed.
        Ensures that the event cannot be modified on the target MISP instances after synchronization.
        """
        # Use the first MISP instance as the source for the event
        source_instance = misps_org_admin[0]

        # Create a new event on the source instance
        event = create_event('\n Event for locked status on push')
        event.distribution = 2  # Set distribution to 'Connected Community'

        event = source_instance.add_event(event, pythonify=True)
        check_response(event)
        self.assertIsNotNone(event.id)
        uuid = event.uuid

        # Publish the event immediately to propagate it to linked instances
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)  # Allow time for synchronization to complete

        # Retrieve the server configurations linked to the source instance
        servers = misps_site_admin[0].servers()
        servers_id = get_servers_id(servers)
        if not servers_id:
            raise Exception("No server configuration found for the source instance")

        # For each linked target instance, verify that the event exists and is locked
        linked_server_numbers = extract_server_numbers(servers)
        for target_index in linked_server_numbers:
            target_instance = misps_org_admin[target_index - 1]
            search_results = target_instance.search(uuid=uuid)
            self.assertGreater(
                len(search_results), 0,
                f"Event not found on MISP_{target_index} after push"
            )
            for result in search_results:
                self.assertTrue(result['Event']['locked'], f"Event on MISP_{target_index} is not locked")

        # Attempt to update the event on each target instance and verify that modification is not allowed
        for target_index in linked_server_numbers:
            target_instance = misps_org_admin[target_index - 1]
            # Try to add an attribute to the locked event
            event_to_update = target_instance.get_event(event, pythonify=True)
            event_to_update.add_attribute('text', 'This should not be allowed')
            target_instance.update_event(event_to_update, pythonify=True)
            # Ensure the event was not modified (should still have only one attribute)
            updated_event = target_instance.search(uuid=uuid)
            self.assertEqual(
                len(updated_event[0]['Event']['Attribute']), 1,
                f"Locked event on MISP_{target_index} must remain unmodified with exactly 1 attribute"
            )

        # Cleanup: remove all test events and blocklists from all instances
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)


    def testLockedStatusOnPull(self):
        """
        Verifies that the 'locked' attribute of an event is correctly set to True when the event is pulled.
        Ensures that the event cannot be modified on the target MISP instance after synchronization.
        """
        # Find a unidirectional synchronization link between two instances
        source_instance, target_instance, source_index, target_index, server_id = find_unidirectional_link()
        print(f"Unidirectional link: {source_index} --> {target_index}")

        # Create a new event on the source instance
        event = create_event('\n Event for locked status on pull')
        event.distribution = 2  # Set distribution to 'Connected Community'
        event = source_instance.add_event(event, pythonify=True)
        check_response(event)
        self.assertIsNotNone(event.id)
        uuid = event.uuid

        # Publish the event immediately to make it available for pulling
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)  # Allow time for synchronization to complete

        # Publish the event again to ensure propagation
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)  # Allow time for synchronization to complete

        # Perform the pull operation on the target instance
        pull_result = misps_site_admin[target_index - 1].server_pull(server=server_id, event=event.id)
        time.sleep(2)  # Allow time for the pull to complete
        check_response(pull_result)

        # Verify that the event exists and is locked on the target instance
        results = target_instance.search(uuid=uuid)
        self.assertGreater(len(results), 0, f"Event not found on MISP_{target_index} after pull")
        for result in results:
            self.assertTrue(result['Event']['locked'], f"Event on MISP_{target_index} is not locked")

        # Attempt to update the event on the target instance and verify that modification is not allowed
        event_to_update = target_instance.get_event(event, pythonify=True)
        event_to_update.add_attribute('text', 'This should not be allowed')
        target_instance.update_event(event_to_update, pythonify=True)
        # Ensure the event was not modified (should still have only one attribute)
        updated_event = target_instance.search(uuid=uuid)
        self.assertEqual(
            len(updated_event[0]['Event']['Attribute']), 1,
            f"Locked event on MISP_{target_index} must remain unmodified with exactly 1 attribute"
        )

        # Cleanup: remove all test events and blocklists from all instances
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)
