import unittest
import time
from common import misps_site_admin, misps_org_admin, create_event, publish_immediately, check_response, get_servers_id, extract_server_numbers, find_unidirectional_link, purge_events_and_blocklists
from pymisp import MISPAttribute


class TestModifyAttribute(unittest.TestCase):
    def testUpdatedAttributeOnPush(self):
        """
        Verifies that when an attribute is updated in the source instance,
        the updated attribute is correctly propagated to all target instances via push.
        The event should be pushed to the target instances with the updated attribute value.
        """
        # Use the first MISP instance as the source
        source_instance = misps_org_admin[0]

        # Create a new event on the source instance
        event = create_event('Event for updated attribute on push')
        event.distribution = 2
        attribute = event.add_attribute('text', 'initial_value')

        # Add the event to the source instance
        event = source_instance.add_event(event, pythonify=True)
        check_response(event)
        self.assertIsNotNone(event.id)
        uuid = event.uuid

        # Publish the event immediately to propagate changes
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)  # Wait for synchronization to complete

        # Retrieve the server configurations linked to the source instance
        servers = misps_site_admin[0].servers()
        servers_id = get_servers_id(servers)
        if not servers_id:
            raise Exception("No server configuration found for the source instance")

        # Push the event to each linked server before publication
        for server_id in servers_id:
            push_response = misps_site_admin[0].server_push(server=server_id, event=event.id)
            time.sleep(2)  # Wait for the push operation to complete
            check_response(push_response)

        # Verify that the event is present on each target instance
        linked_server_numbers = extract_server_numbers(servers)
        for target_index in linked_server_numbers:
            target_instance = misps_org_admin[target_index - 1]
            search_results = target_instance.search(uuid=uuid)
            self.assertGreater(
                len(search_results), 0,
                f"Event not found on MISP_{target_index} after push"
            )

        # Update the attribute value on the source instance
        attribute.value = 'updated_value'
        updated_attribute = source_instance.update_attribute(attribute, pythonify=True)
        check_response(updated_attribute)

        # Publish the event again to propagate the updated attribute
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)  # Wait for synchronization to complete

        # Verify that the updated attribute is present on each target instance
        for target_index in linked_server_numbers:
            target_instance = misps_org_admin[target_index - 1]
            search_results = target_instance.search(uuid=uuid)
            self.assertGreater(
                len(search_results), 0,
                f"Event not found on MISP_{target_index} after attribute update"
            )
            for result in search_results:
                attributes = result['Event']['Attribute']
                found = False
                for attr in attributes:
                    if attr['value'] == 'updated_value':
                        found = True
                        break
                self.assertTrue(found, f"Updated attribute not found on MISP_{target_index}")

        # Cleanup: delete all test events and blocklists on all instances
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)


    def testUpdatedAttributeOnPull(self):
        """
        Verifies that when an attribute is updated in the source instance,
        the updated attribute is correctly pulled to the target instances.
        The event should be pulled from the source instance with the updated attribute value.
        """
        # Find a unidirectional link between two instances
        source_instance, target_instance, source_index, target_index, server_id = find_unidirectional_link()
        print(f"Unidirectional link: {source_index} --> {target_index}")

        # Create a new event on the source instance
        event_name = f"Event {source_index} for pull on {target_index} with updated attribute"
        event = create_event(event_name)
        event.distribution = 2
        attribute = event.add_attribute('text', 'initial_value')

        # Add the event to the source instance
        event = source_instance.add_event(event, pythonify=True)
        check_response(event)
        self.assertIsNotNone(event.id)
        uuid = event.uuid

        # Publish the event immediately
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)  # Wait for synchronization to complete

        # Perform the pull operation on the target instance
        pull_result = misps_site_admin[target_index - 1].server_pull(server=server_id, event=event.id)
        time.sleep(2)  # Wait for the pull operation to complete
        check_response(pull_result)

        # Confirm that the event exists on the target instance
        found = False
        results = target_instance.search(uuid=uuid)
        if results:
            found = True
            for result in results:
                attributes = result['Event']['Attribute']
                found_attr = False
                for attr in attributes:
                    if attr['value'] == 'initial_value':
                        found_attr = True
                        break
                self.assertTrue(found_attr, f"Initial attribute not found on MISP_{target_index}")

        self.assertTrue(found, f"Event not found on MISP_{target_index} after pull")

        # Update the attribute value on the source instance
        attribute.value = 'updated_value'
        updated_attribute = source_instance.update_attribute(attribute, pythonify=True)
        check_response(updated_attribute)

        # Publish the updated event immediately
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)  # Wait for synchronization to complete

        # Perform the pull operation again to get the updated attribute
        pull_result = misps_site_admin[target_index - 1].server_pull(server=server_id, event=event.id)
        time.sleep(2)  # Wait for the pull operation to complete
        check_response(pull_result)

        # Confirm that the updated attribute exists on the target instance
        results = target_instance.search(uuid=uuid)
        found = False
        if results:
            found = True
            for result in results:
                attributes = result['Event']['Attribute']
                found_attr = False
                for attr in attributes:
                    if attr['value'] == 'updated_value':
                        found_attr = True
                        break
                self.assertTrue(found_attr, f"Updated attribute not found on MISP_{target_index}")

        self.assertTrue(found, f"Event not found on MISP_{target_index} after pull with updated attribute")

        # Cleanup: delete all test events and blocklists on all instances
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)


    def testSoftDeleteAttributeOnPush(self):
        """
        Verifies that when an attribute is soft-deleted in the source instance,
        the soft-deleted attribute is correctly propagated to all target instances via push.
        The event should be pushed to the target instances with the soft-deleted attribute.
        """
        # Use the first MISP instance as the source
        source_instance = misps_org_admin[0]

        # Create a new event on the source instance
        event = create_event('Event for soft delete attribute on push')
        event.distribution = 2
        attribute = event.add_attribute('text', 'Gotta be deleted')

        # Add the event to the source instance
        event = source_instance.add_event(event, pythonify=True)
        check_response(event)
        self.assertIsNotNone(event.id)
        uuid = event.uuid

        # Publish the event immediately
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)  # Wait for synchronization to complete

        # Retrieve the server configurations linked to the source instance
        servers = misps_site_admin[0].servers()
        servers_id = get_servers_id(servers)
        if not servers_id:
            raise Exception("No server configuration found for the source instance")

        # Verify that the event is present on each target instance
        linked_server_numbers = extract_server_numbers(servers)
        for target_index in linked_server_numbers:
            target_instance = misps_org_admin[target_index - 1]
            search_results = target_instance.search(uuid=uuid)
            self.assertGreater(
                len(search_results), 0,
                f"Event not found on MISP_{target_index} after push"
            )

        # Soft delete the attribute on the source instance
        attribute.delete()
        updated_attribute = source_instance.update_attribute(attribute, pythonify=True)
        check_response(updated_attribute)

        # Publish the event again to propagate the soft-deleted attribute
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)

        # Verify that the soft-deleted attribute is present on each target instance
        for target_index in linked_server_numbers:
            target_instance = misps_org_admin[target_index - 1]
            search_results = misps_site_admin[target_index - 1].search(uuid=uuid, deleted=True)
            self.assertGreater(
                len(search_results), 0,
                f"Event not found on MISP_{target_index} after attribute soft delete"
            )
            for result in search_results:
                attributes = result['Event']['Attribute']
                found = False
                for attr in attributes:
                    if attr['value'] == 'Gotta be deleted' and attr['deleted'] is True:
                        found = True
                        break
                self.assertTrue(found, f"Soft-deleted attribute not found on MISP_{target_index}")

        # Cleanup: delete all test events and blocklists on all instances
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)


    def testSoftDeleteAttributeOnPull(self):
        """
        Verifies that when an attribute is soft-deleted in the source instance,
        the soft-deleted attribute is correctly pulled to the target instances.
        The event should be pulled from the source instance with the soft-deleted attribute.
        """
        # Find a unidirectional link between two instances
        source_instance, target_instance, source_index, target_index, server_id = find_unidirectional_link()
        print(f"Unidirectional link: {source_index} --> {target_index}")

        # Create a new event on the source instance
        event_name = f"Event {source_index} for pull on {target_index} with soft-deleted attribute"
        event = create_event(event_name)
        event.distribution = 2
        attribute = event.add_attribute('text', 'Gotta be deleted')

        # Add the event to the source instance
        event = source_instance.add_event(event, pythonify=True)
        check_response(event)
        self.assertIsNotNone(event.id)
        uuid = event.uuid

        # Publish the event immediately
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)  # Wait for synchronization to complete 

        # Perform the pull operation on the target instance
        pull_result = misps_site_admin[target_index - 1].server_pull(server=server_id, event=event.id)
        time.sleep(2)
        check_response(pull_result)

        # Confirm that the event exists on the target instance
        found = False
        results = target_instance.search(uuid=uuid)
        if results:
            found = True
            for result in results:
                attributes = result['Event']['Attribute']
                found_attr = False
                for attr in attributes:
                    if attr['value'] == 'Gotta be deleted':
                        found_attr = True
                        break
                self.assertTrue(found_attr, f"Initial attribute not found on MISP_{target_index}")

        self.assertTrue(found, f"Event not found on MISP_{target_index} after pull")

        # Soft delete the attribute on the source instance
        attribute.delete()
        updated_attribute = source_instance.update_attribute(attribute, pythonify=True)
        check_response(updated_attribute)

        # Publish the updated event immediately
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)  # Wait for synchronization to complete

        # Perform the pull operation again to get the soft-deleted attribute
        pull_result = misps_site_admin[target_index - 1].server_pull(server=server_id, event=event.id)
        time.sleep(2)  # Wait for the pull operation to complete
        check_response(pull_result)

        # Confirm that the soft-deleted attribute exists on the target instance
        results = misps_site_admin[target_index - 1].search(uuid=uuid, deleted=True) # Site admin required to search deleted attributes
        found = False
        if results:
            found = True
            for result in results:
                attributes = result['Event']['Attribute']
                found_attr = False
                for attr in attributes:
                    if attr['value'] == 'Gotta be deleted' and attr['deleted'] is True:
                        found_attr = True
                        break
                self.assertTrue(found_attr, f"Soft-deleted attribute not found on MISP_{target_index}")

        self.assertTrue(found, f"Event not found on MISP_{target_index} after pull with soft-deleted attribute")

        # Cleanup: delete all test events and blocklists on all instances
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)


    def testUpdatedProposalAttributeOnPush(self):
        """
        Verifies that when a proposal attribute is updated in the source instance,
        the updated proposal attribute is correctly propagated to all target instances via push.
        The event should be pushed to the target instances with the updated proposal attribute.
        """
        # Use the first MISP instance as the source
        source_instance = misps_org_admin[0]

        # Create a new event on the source instance
        event = create_event('Event for updated proposal attribute on push')
        event.distribution = 2
        event = source_instance.add_event(event, pythonify=True)
        check_response(event)
        self.assertIsNotNone(event.id)
        uuid = event.uuid

        # Add a new attribute to the event
        new_attribute = MISPAttribute()
        new_attribute.value = 'John'
        new_attribute.type = 'first-name'
        new_attribute = source_instance.add_attribute(event, new_attribute, pythonify=True)

        # Add the first proposal attribute
        first_new_proposal = MISPAttribute()
        first_new_proposal.value = 'Doe'
        first_new_proposal.type = 'last-name'
        print(f"UUID of the proposal: {first_new_proposal.uuid}")
        first_new_proposal = source_instance.add_attribute_proposal(event.id, first_new_proposal)
        print(f"UUID of the proposal: {first_new_proposal}")

        # Add the second proposal attribute
        second_new_proposal = MISPAttribute()
        second_new_proposal.value = 'Dope'
        second_new_proposal.type = 'last-name'
        second_new_proposal = source_instance.add_attribute_proposal(event.id, second_new_proposal)

        # Publish the event immediately
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)  # Wait for synchronization to complete

        # Retrieve the server configurations linked to the source instance
        servers = misps_site_admin[0].servers()
        servers_id = get_servers_id(servers)
        if not servers_id:
            raise Exception("No server configuration found for the source instance")

        # Perform the push operation on all linked servers (proposals are not shared with a single publication)
        for server_id in servers_id:
            push_response = misps_site_admin[0].server_push(server=server_id, event=event.id)
            time.sleep(2)  # Wait for the push operation to complete
            check_response(push_response)

        # Verify that the event is present on each target instance with the proposal attribute
        linked_server_numbers = extract_server_numbers(servers)
        for target_index in linked_server_numbers:
            target_instance = misps_org_admin[target_index - 1]
            search_results = target_instance.search(uuid=uuid)
            self.assertGreater(
                len(search_results), 0,
                f"Event not found on MISP_{target_index} after push"
            )
            for result in search_results:
                proposal = result['Event']['ShadowAttribute']
                found_proposal = False
                for prop in proposal:
                    if prop['value'] == 'Doe':
                        found_proposal = True
                        break
                self.assertTrue(found_proposal, f"Proposal attribute not found on MISP_{target_index}")

        # Accept the first proposal and reject the second one
        #print(f"UUID of the proposal: {first_new_proposal}")
        response = source_instance.accept_attribute_proposal(first_new_proposal)
        #print(f"Response after accepting first proposal: {response}")
        #self.assertEqual(response['errors'], 'Proposed change accepted.')
        response = source_instance.discard_attribute_proposal(second_new_proposal)

        # Publish the event immediately
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)

        # Perform the push operation again to propagate the updated proposals
        for server_id in servers_id:
            push_response = misps_site_admin[0].server_push(server=server_id, event=event.id)
            time.sleep(2)  # Wait for the push operation to complete
            check_response(push_response)

        # Verify that the first proposal is present as an attribute on each target instance and the second proposal is not present
        for target_index in linked_server_numbers:
            target_instance = misps_org_admin[target_index - 1]
            search_results = target_instance.search(uuid=uuid)
            self.assertGreater(
                len(search_results), 0,
                f"Event not found on MISP_{target_index} after proposal update"
            )
            for result in search_results:
                attributes = result['Event']['Attribute']
                found_first_proposal = False
                found_second_proposal = False
                for attr in attributes:
                    if attr['value'] == 'Doe':
                        found_first_proposal = True
                    if attr['value'] == 'Dope':
                        found_second_proposal = True
                self.assertTrue(found_first_proposal, f"Accepted proposal not found on MISP_{target_index}")
                self.assertFalse(found_second_proposal, f"Discarded proposal found on MISP_{target_index}")

        # Cleanup: delete all test events and blocklists on all instances
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)



    def testUpdatedProposalAttributeOnPull(self):
        """
        Verifies that when a proposal attribute is updated in the source instance,
        the updated proposal attribute is correctly pulled to the target instances.
        The event should be pulled from the source instance with the updated proposal attribute.
        """
        # Find a unidirectional link between two instances
        source_instance, target_instance, source_index, target_index, server_id = find_unidirectional_link()
        print(f"Unidirectional link: {source_index} --> {target_index}")

        # Create a new event on the source instance
        event_name = f"Event {source_index} for pull on {target_index} with updated proposal attribute"
        event = create_event(event_name)
        event.distribution = 2
        event = source_instance.add_event(event, pythonify=True)
        check_response(event)
        self.assertIsNotNone(event.id)
        uuid = event.uuid

        # Add a new attribute to the event
        new_attribute = MISPAttribute()
        new_attribute.value = 'John'
        new_attribute.type = 'first-name'
        new_attribute = source_instance.add_attribute(event, new_attribute, pythonify=True)

        # Add the first proposal attribute
        first_new_proposal = MISPAttribute()
        first_new_proposal.value = 'Doe'
        first_new_proposal.type = 'last-name'
        first_new_proposal = source_instance.add_attribute_proposal(event.id, first_new_proposal)

        # Add the second proposal attribute
        second_new_proposal = MISPAttribute()
        second_new_proposal.value = 'Dope'
        second_new_proposal.type = 'last-name'
        second_new_proposal = source_instance.add_attribute_proposal(event.id, second_new_proposal)

        # Publish the event immediately
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)  # Wait for synchronization to complete

        # Perform the pull operation on the target instance
        pull_result = misps_site_admin[target_index - 1].server_pull(server=server_id)
        time.sleep(2) # Wait for the pull operation to complete
        check_response(pull_result)

        # Confirm that the event exists on the target instance with the proposal attribute
        found = False
        results = target_instance.search(uuid=uuid)
        if results:
            found = True
            for result in results:
                proposal = result['Event']['ShadowAttribute']
                found_proposal = False
                for prop in proposal:
                    if prop['value'] == 'Doe':
                        found_proposal = True
                        break
                self.assertTrue(found_proposal, f"Proposal attribute not found on MISP_{target_index}")

        self.assertTrue(found, f"Event not found on MISP_{target_index} after pull")

        # Accept the first proposal and reject the second one
        response = source_instance.accept_attribute_proposal(first_new_proposal)
        #print(f"Response after accepting first proposal: {response}")
        #self.assertEqual(response['errors'], 'Proposed change accepted.')
        response = source_instance.discard_attribute_proposal(second_new_proposal)

        # Publish the event immediately
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)

        # Perform the pull operation again to propagate the updated proposals
        pull_result = misps_site_admin[target_index - 1].server_pull(server=server_id)
        time.sleep(2)  # Wait for the pull operation to complete
        check_response(pull_result)

        # Verify that the first proposal is present as an attribute on the target instance and the second proposal is not present
        results = target_instance.search(uuid=uuid)
        found = False
        if results:
            found = True
            for result in results:
                attributes = result['Event']['Attribute']
                found_first_proposal = False
                found_second_proposal = False
                for attr in attributes:
                    if attr['value'] == 'Doe':
                        found_first_proposal = True
                    if attr['value'] == 'Dope':
                        found_second_proposal = True
                self.assertTrue(found_first_proposal, f"Accepted proposal not found on MISP_{target_index}")
                self.assertFalse(found_second_proposal, f"Discarded proposal found on MISP_{target_index}")

        # Cleanup: delete all test events and blocklists on all instances
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)


    def testDeletedProposalAttributeOnPush(self):
        """
        Verifies that when a proposal to delete an attribute is made in the source instance,
        the deleted proposal attribute is correctly propagated to all target instances via push.
        The event should be pushed to the target instances with the deleted proposal attribute.
        """
        # Use the first MISP instance as the source
        source_instance = misps_org_admin[0]

        # Create a new event on the source instance
        event = create_event('Event for deleted proposal attribute on push')
        event.distribution = 2
        event = source_instance.add_event(event, pythonify=True)
        check_response(event)
        self.assertIsNotNone(event.id)
        uuid = event.uuid

        # Add a new attribute to the event
        new_attribute = MISPAttribute()
        new_attribute.value = 'John'
        new_attribute.type = 'first-name'
        new_attribute = source_instance.add_attribute(event, new_attribute, pythonify=True)

        # Propose the soft deletion of the attribute
        response = source_instance.delete_attribute_proposal(new_attribute)
        print("Response after proposing deletion:", response)

        # Publish the event immediately
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)  # Wait for synchronization to complete

        # Retrieve the server configurations linked to the source instance
        servers = misps_site_admin[0].servers()
        servers_id = get_servers_id(servers)
        if not servers_id:
            raise Exception("No server configuration found for the source instance")

        # Perform the push operation on all linked servers (proposals are not shared with a single publication)
        for server_id in servers_id:
            push_response = misps_site_admin[0].server_push(server=server_id)
            time.sleep(2)  # Wait for the push operation to complete
            check_response(push_response)

        # Verify that the event is present on each target instance with the proposal attribute
        linked_server_numbers = extract_server_numbers(servers)
        for target_index in linked_server_numbers:
            target_instance = misps_org_admin[target_index - 1]
            search_results = target_instance.search(uuid=uuid)
            self.assertGreater(
                len(search_results), 0,
                f"Event not found on MISP_{target_index} after push"
            )
            for result in search_results:
                attributes = result['Event']['Attribute']
                found_proposal = False
                for attr in attributes:
                    if attr['value'] == 'John':
                        for prop in attr['ShadowAttribute']:
                            if prop['proposal_to_delete'] is True:
                                found_proposal = True
                                break
                self.assertTrue(found_proposal, f"Proposal attribute not found on MISP_{target_index}")

        # Cleanup: delete all test events and blocklists on all instances
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)


    def testDeletedProposalAttributeOnPull(self):
        """
        Verifies that when a proposal to delete an attribute is made in the source instance,
        the deleted proposal attribute is correctly pulled to the target instances.
        The event should be pulled from the source instance with the deleted proposal attribute.
        """
        # Find a unidirectional link between two instances
        source_instance, target_instance, source_index, target_index, server_id = find_unidirectional_link()
        print(f"Unidirectional link: {source_index} --> {target_index}")

        # Create a new event on the source instance
        event_name = f"Event {source_index} for pull on {target_index} with deleted proposal attribute"
        event = create_event(event_name)
        event.distribution = 2
        event = source_instance.add_event(event, pythonify=True)
        check_response(event)
        self.assertIsNotNone(event.id)
        uuid = event.uuid

        # Add a new attribute to the event
        new_attribute = MISPAttribute()
        new_attribute.value = 'John'
        new_attribute.type = 'first-name'
        new_attribute = source_instance.add_attribute(event, new_attribute, pythonify=True)

        # Propose the soft deletion of the attribute
        response = source_instance.delete_attribute_proposal(new_attribute)
        print("Response after proposing deletion:", response)

        # Publish the event immediately
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)  # Wait for synchronization to complete

        # Perform the pull operation on the target instance
        pull_result = misps_site_admin[target_index - 1].server_pull(server=server_id)
        time.sleep(2)  # Wait for the pull operation to complete
        check_response(pull_result)

        # Confirm that the event exists on the target instance with the proposal attribute
        found = False
        results = target_instance.search(uuid=uuid)
        if results:
            found = True
            for result in results:
                attributes = result['Event']['Attribute']
                found_proposal = False
                for attr in attributes:
                    if attr['value'] == 'John':
                        for prop in attr['ShadowAttribute']:
                            if prop['proposal_to_delete'] is True:
                                found_proposal = True
                                break
                self.assertTrue(found_proposal, f"Proposal attribute not found on MISP_{target_index}")

        self.assertTrue(found, f"Event not found on MISP_{target_index} after pull")

        # Cleanup: delete all test events and blocklists on all instances
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)

