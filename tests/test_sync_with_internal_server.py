import unittest
import time
import uuid as UUID
from common import misps_site_admin, misps_org_admin, create_event, publish_immediately, check_response, get_servers_id, extract_server_numbers, purge_events_and_blocklists
from pymisp import MISPTag, MISPGalaxy, MISPGalaxyCluster

class TestSyncWithInternalServer(unittest.TestCase):
    def testLocalShareAndDowngradeOnPush(self):
        """
        Creates an event with distribution level 0 on the last instance in the topology,
        publishes it, then checks that it is present on the target server with the same distribution level.
        Repeats for distribution levels 1, 2, and 3.
        """
        # Get the last instance in the topology
        source_instance = misps_org_admin[-1]
        source_index = len(misps_org_admin)

        # Get the servers linked to this instance
        servers = misps_site_admin[-1].servers()
        servers_id = get_servers_id(servers)
        linked_server_numbers = extract_server_numbers(servers)
        if not servers_id or not linked_server_numbers:
            self.skipTest("No linked server found for the last instance.")

        # Use the first linked server as the target
        target_index = linked_server_numbers[0]
        target_instance = misps_org_admin[target_index - 1]
        server_id = servers_id[0]

        for dist_level in range(4):
            # Create an event with the current distribution level
            event = create_event(f'Event for local share and downgrade on push (dist={dist_level})')
            event.distribution = dist_level
            event = source_instance.add_event(event, pythonify=True)
            check_response(event)
            self.assertIsNotNone(event.id)
            uuid = event.uuid

            # Publish the event immediately
            publish_immediately(source_instance, event, with_email=False)
            time.sleep(2)

            # Push the event to the target server
            push_result = misps_site_admin[-1].server_push(server=server_id, event=event.id)
            time.sleep(2)
            check_response(push_result)

            # Check that the event is present on the target server with the same distribution level
            results = target_instance.search(uuid=uuid)
            self.assertGreater(len(results), 0, f"Event not found on target server MISP_{target_index} after push (dist={dist_level})")
            for result in results:
                self.assertEqual(
                    int(result['Event']['distribution']), dist_level,
                    f"Incorrect distribution on MISP_{target_index} (expected {dist_level}, got {result['Event']['distribution']})"
                )

        # Cleanup: delete all test events on all instances
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)

    def testLocalShareAndDowngradeOnPull(self):
        """
        Creates events with different distribution levels on the last instance in the topology.
        Each event is published, then a server_pull is performed from a linked server.
        Checks that the distribution level is correctly downgraded according to the defined rules.
        """
        # Get the last instance in the topology
        source_instance = misps_org_admin[-1]
        source_index = len(misps_org_admin)

        # Get the servers linked to this instance
        servers = misps_site_admin[-1].servers()
        servers_id = get_servers_id(servers)
        linked_server_numbers = extract_server_numbers(servers)
        if not servers_id or not linked_server_numbers:
            self.skipTest("No linked server found for the last instance.")

        # Use the first linked server as the target
        target_index = linked_server_numbers[0]
        target_instance = misps_org_admin[target_index - 1]
        server_id = get_servers_id(misps_site_admin[target_index - 1].servers())[0]

        # Expected mapping of distribution levels after pull
        expected_distribution_after_pull = {
            0: 0,  # Organisation only → no downgrade
            1: 0,  # This community → downgrade to 0
            2: 1,  # Connected community → downgrade to 1
            3: 3   # All communities → no downgrade
        }

        for dist_level in range(4):
            print(f"Testing initial distribution = {dist_level}")

            # Create an event with the desired distribution
            event = create_event(f'Event for local share and downgrade on pull (dist={dist_level})')
            event.distribution = dist_level
            event = source_instance.add_event(event, pythonify=True)
            check_response(event)
            self.assertIsNotNone(event.id)
            uuid = event.uuid

            # Publish the event
            publish_immediately(source_instance, event, with_email=False)
            time.sleep(2)

            # Clean up existing events and blocklists on the target side
            purge_events_and_blocklists(target_instance)

            # Perform the pull from the target
            pull_result = misps_site_admin[target_index - 1].server_pull(server=server_id)
            time.sleep(2)
            check_response(pull_result)

            # Search for the event on the target
            results = misps_site_admin[target_index - 1].search(uuid=uuid)
            self.assertGreater(len(results), 0, f"Event not found on MISP_{target_index} after pull")

            # Check that the distribution was correctly applied
            for result in results:
                actual_distribution = int(result['Event']['distribution'])
                expected_distribution = expected_distribution_after_pull[dist_level]
                self.assertEqual(
                    actual_distribution, expected_distribution,
                    f"Incorrect distribution on MISP_{target_index}: expected {expected_distribution}, got {actual_distribution} (source={dist_level})"
                )

            # Cleanup: delete all test events on all instances
            for instance in misps_site_admin:
                purge_events_and_blocklists(instance)


    def testLockedFlagOnPush(self):
        """
        Creates an event (locked=False) on the last instance in the topology,
        publishes the event, performs a server_push to a linked server,
        then checks that the event is present on the target server with locked=True.
        """
        # Get the last instance in the topology
        source_instance = misps_org_admin[-1]

        # Get the servers linked to this instance
        servers = misps_site_admin[-1].servers()
        servers_id = get_servers_id(servers)
        linked_server_numbers = extract_server_numbers(servers)
        if not servers_id or not linked_server_numbers:
            self.skipTest("No linked server found for the last instance.")

        # Use the first linked server as the target
        target_index = linked_server_numbers[0]
        target_instance = misps_org_admin[target_index - 1]

        # Create an event (locked=False by default)
        event = create_event('Event for locked flag on push')
        event.distribution = 2
        event = source_instance.add_event(event, pythonify=True)
        check_response(event)
        self.assertIsNotNone(event.id)
        uuid = event.uuid

        # Check that the event is unlocked on the source
        event_on_source = source_instance.get_event(event.id, pythonify=True)
        self.assertFalse(
            getattr(event_on_source, 'locked', False),
            "The event should be unlocked on the source"
        )

        # Publish the event immediately
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)

        # Check that the event is present on the target server with locked=True
        results = target_instance.search(uuid=uuid)
        self.assertGreater(len(results), 0, f"Event not found on target server MISP_{target_index} after push")
        for result in results:
            self.assertTrue(
                result['Event'].get('locked', False),
                f"Incorrect locked flag on MISP_{target_index} (expected True, got {result['Event'].get('locked')})"
            )

        # Cleanup: delete all test events on all instances
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)


    def testLockedFlagOnPull(self):
        """
        Creates an event (locked=False) on the last instance in the topology,
        publishes the event, performs a server_pull from a linked server,
        then checks that the event is present on the target server with locked=True.
        """
        # Get the last instance in the topology
        source_instance = misps_org_admin[-1]
        source_index = len(misps_org_admin)

        # Get the servers linked to this instance
        servers = misps_site_admin[-1].servers()
        servers_id = get_servers_id(servers)
        linked_server_numbers = extract_server_numbers(servers)
        if not servers_id or not linked_server_numbers:
            self.skipTest("No linked server found for the last instance.")

        # Use the first linked server as the target
        target_index = linked_server_numbers[0]
        target_instance = misps_org_admin[target_index - 1]
        server_id = get_servers_id(misps_site_admin[target_index - 1].servers())[0]

        # Create an event (locked=False by default)
        event = create_event('Event for locked flag on pull')
        event.distribution = 2
        event = source_instance.add_event(event, pythonify=True)
        check_response(event)
        self.assertIsNotNone(event.id)
        uuid = event.uuid

        # Check that the event is unlocked on the source
        event_on_source = source_instance.get_event(event.id, pythonify=True)
        self.assertFalse(getattr(event_on_source, 'locked', False), "The event should be unlocked on the source")

        # Publish the event immediately
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)

        # Clean up existing events and blocklists on the target side
        purge_events_and_blocklists(target_instance)

        # Perform a server_pull on the target server
        pull_result = misps_site_admin[target_index - 1].server_pull(server=server_id)
        time.sleep(2)
        check_response(pull_result)

        # Check that the event is present on the target server with locked=True
        results = target_instance.search(uuid=uuid)
        self.assertGreater(len(results), 0, f"Event not found on target server MISP_{target_index} after pull")
        for result in results:
            self.assertTrue(
                result['Event'].get('locked', False),
                f"Incorrect locked flag on MISP_{target_index} (expected True, got {result['Event'].get('locked')})"
            )

        # Cleanup: delete all test events on all instances
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)


    def testLocalTagPropagationOnPush(self):
        """
        Tests that local tags (local_only=True) are properly propagated between internal servers during a push.
        """
        # Get the last instance in the topology
        source_instance = misps_org_admin[-1]
        source_index = len(misps_org_admin)

        # Get the servers linked to this instance
        servers = misps_site_admin[-1].servers()
        servers_id = get_servers_id(servers)
        linked_server_numbers = extract_server_numbers(servers)
        if not servers_id or not linked_server_numbers:
            self.skipTest("No linked server found for the last instance.")

        # Use the first linked server as the target
        target_index = linked_server_numbers[0]
        target_instance = misps_org_admin[target_index - 1]

        # Create the event
        event = create_event('Event with a local tag')
        event.distribution = 2
        event = source_instance.add_event(event, pythonify=True)
        check_response(event)
        self.assertIsNotNone(event.id)
        uuid = event.uuid

        # Create tags
        local_tag = MISPTag()
        local_tag.name = 'This is a local tag'
        local_tag.local_only = True
        new_local_tag = source_instance.add_tag(local_tag, pythonify=True)
        check_response(new_local_tag)

        global_tag = MISPTag()
        global_tag.name = 'This is not a local tag'
        new_global_tag = source_instance.add_tag(global_tag, pythonify=True)
        check_response(new_global_tag)

        # Add tags to the event
        source_instance.tag(event, new_local_tag.name, local=True)
        source_instance.tag(event, new_global_tag.name)

        # Publish the event
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)

        # Check on the target server
        results = target_instance.search(uuid=uuid)
        self.assertGreater(len(results), 0, f"The event was not found on MISP_{target_index} after the push.")

        for result in results:
            tags = result['Event']['Tag']
            found_local_tag = any(tag["name"] == new_local_tag.name for tag in tags)
            found_global_tag = any(tag["name"] == new_global_tag.name for tag in tags)

            self.assertTrue(found_global_tag, f"Global tag not found on MISP_{target_index}")
            self.assertTrue(found_local_tag, f"Local tag not found on MISP_{target_index}")

        # Cleanup: delete events and tags on all relevant instances
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)

        misps_site_admin[-1].delete_tag(new_local_tag)
        misps_site_admin[-1].delete_tag(new_global_tag)



    def testLocalTagPropagationOnPull(self):
        """
        Tests that local tags (local_only=True) are properly propagated during a pull between internal servers.
        """
        # Get the last instance in the topology
        source_instance = misps_org_admin[-1]
        source_index = len(misps_org_admin)

        # Get the servers linked to this instance
        servers = misps_site_admin[-1].servers()
        servers_id = get_servers_id(servers)
        linked_server_numbers = extract_server_numbers(servers)
        if not servers_id or not linked_server_numbers:
            self.skipTest("No linked server found for the last instance.")

        # Use the first linked server as the target
        target_index = linked_server_numbers[0]
        target_instance = misps_org_admin[target_index - 1]
        server_id = get_servers_id(misps_site_admin[target_index - 1].servers())[0]

        # Create the event
        event_name = f"Event {source_index} with a local tag for pull on {target_index}"
        event = create_event(event_name)
        event.distribution = 2
        event = source_instance.add_event(event, pythonify=True)
        check_response(event)
        self.assertIsNotNone(event.id)
        uuid = event.uuid

        # Create tags
        local_tag = MISPTag()
        local_tag.name = 'This is a local tag'
        local_tag.local_only = True
        new_local_tag = source_instance.add_tag(local_tag, pythonify=True)
        check_response(new_local_tag)

        global_tag = MISPTag()
        global_tag.name = 'This is not a local tag'
        new_global_tag = source_instance.add_tag(global_tag, pythonify=True)
        check_response(new_global_tag)

        # Add tags to the event
        source_instance.tag(event, new_local_tag.name, local=True)
        source_instance.tag(event, new_global_tag.name)

        # Publish the event
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)

        # Pull from the target server
        purge_events_and_blocklists(target_instance)
        pull_result = misps_site_admin[target_index - 1].server_pull(server=server_id)
        time.sleep(2)
        check_response(pull_result)

        # Check for the presence of tags on the target
        results = target_instance.search(uuid=uuid)
        self.assertGreater(len(results), 0, f"Event not found on MISP_{target_index}")

        for result in results:
            tags = result['Event']['Tag']
            found_local_tag = any(tag["name"] == new_local_tag.name for tag in tags)
            found_global_tag = any(tag["name"] == new_global_tag.name for tag in tags)

            self.assertTrue(found_global_tag, f"Global tag not found on MISP_{target_index}")
            self.assertTrue(found_local_tag, f"Local tag not found on MISP_{target_index}")

        # Cleanup: delete all test events and tags on all instances
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)

        source_instance.delete_tag(new_local_tag)
        source_instance.delete_tag(new_global_tag)




    def testLocalGalaxyClusterPropagationOnPush(self):
        """
        Tests that local Galaxy clusters (local_only=True) are properly propagated during a push between internal servers.
        """
        # Get the last instance
        source_instance = misps_org_admin[-1]
        source_index = len(misps_org_admin)

        # Get the servers linked to this instance
        servers = misps_site_admin[-1].servers()
        servers_id = get_servers_id(servers)
        linked_server_numbers = extract_server_numbers(servers)
        if not servers_id or not linked_server_numbers:
            self.skipTest("No linked server found for the last instance.")

        target_index = linked_server_numbers[0]
        target_instance = misps_org_admin[target_index - 1]


        # Create an event
        event = create_event("Event with local Galaxy Cluster (push)")
        event.distribution = 2
        event = source_instance.add_event(event, pythonify=True)
        check_response(event)
        self.assertIsNotNone(event.id)
        uuid = event.uuid

        #Create a galaxy (not implemented in PyMisp)
        source_instance._check_response(source_instance._prepare_request(
            'POST',
            '/galaxies/add',
            data={
                'name': 'Galaxy for Push',
                'namespace': 'MISP Test',
                'distribution': 2,
                'description': 'testLocalGalaxyClusterPropagationOnPush'
            }
        ))
        new_galaxy = source_instance.galaxies(pythonify=True)[-1]

        # Create a galaxy cluster
        new_uuid = str(UUID.uuid4())
        new_galaxy_cluster: MISPGalaxyCluster = MISPGalaxyCluster()
        new_galaxy_cluster.uuid = new_uuid
        new_galaxy_cluster.value = "Cluster for Push"
        new_galaxy_cluster.authors = ["CIRCL"]
        new_galaxy_cluster.distribution = 2
        new_galaxy_cluster.description = "A cluster description"
        source_instance.add_galaxy_cluster(new_galaxy, new_galaxy_cluster, pythonify=True)

        # Publish the galaxy cluster
        source_instance.publish_galaxy_cluster(new_uuid)
        time.sleep(2)

        # Retrieve a cluster from the first available galaxy
        galaxies: list[MISPGalaxy] = source_instance.galaxies(pythonify=True)
        self.assertGreater(len(galaxies), 0, "No galaxy available")
        galaxy: MISPGalaxy = galaxies[-1]
        galaxy = source_instance.get_galaxy(galaxy.id, withCluster=True, pythonify=True)
        cluster: MISPGalaxyCluster = galaxy.clusters[0]

        # Attach the cluster as a local tag to the event
        source_instance.attach_galaxy_cluster(event, cluster, local=True)
        event = source_instance.get_event(event.id, pythonify=True)
        self.assertEqual(len(event.galaxies), 1)

        # Publish the event
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)

        # Check on the target server
        results = target_instance.search(uuid=uuid)
        self.assertGreater(len(results), 0, f"The event was not found on MISP_{target_index} after the push.")

        for result in results:
            galaxies = result['Event'].get('Galaxy', [])
            found = False
            for galaxy_data in galaxies:
                for cluster_data in galaxy_data.get('GalaxyCluster', []):
                    if str(cluster_data['uuid']) == str(cluster.uuid):
                        found = True
                        break
                if found:
                    break
            self.assertTrue(found, f"Local cluster {cluster.uuid} not found on MISP_{target_index}")

        # Cleanup: delete all test events on all instances
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)





    def testLocalGalaxyClusterPropagationOnPull(self):
        """
        Tests that local Galaxy clusters (local_only=True) are properly propagated during a pull between internal servers.
        """
        # Get the last instance
        source_instance = misps_org_admin[-1]
        source_index = len(misps_org_admin)

        # Get the servers linked to this instance
        servers = misps_site_admin[-1].servers()
        servers_id = get_servers_id(servers)
        linked_server_numbers = extract_server_numbers(servers)
        if not servers_id or not linked_server_numbers:
            self.skipTest("No linked server found for the last instance.")

        target_index = linked_server_numbers[0]
        target_instance = misps_org_admin[target_index - 1]
        server_id = get_servers_id(misps_site_admin[target_index - 1].servers())[0]

        # Create the event
        event = create_event("Event with local Galaxy Cluster (pull)")
        event.distribution = 2
        event = source_instance.add_event(event, pythonify=True)
        check_response(event)
        self.assertIsNotNone(event.id)
        uuid = event.uuid

        #Create a galaxy (not implemented in PyMisp)
        source_instance._check_response(source_instance._prepare_request(
            'POST',
            '/galaxies/add',
            data={
                'name': 'Galaxy for Pull',
                'namespace': 'MISP Test',
                'distribution': 2,
                'description': 'testLocalGalaxyClusterPropagationOnPull'
            }
        ))
        new_galaxy = source_instance.galaxies(pythonify=True)[-1]

        # Create a galaxy cluster
        new_uuid = str(UUID.uuid4())
        new_galaxy_cluster: MISPGalaxyCluster = MISPGalaxyCluster()
        new_galaxy_cluster.uuid = new_uuid
        new_galaxy_cluster.value = "Cluster for Pull"
        new_galaxy_cluster.authors = ["CIRCL"]
        new_galaxy_cluster.distribution = 2
        new_galaxy_cluster.description = "A cluster description"
        source_instance.add_galaxy_cluster(new_galaxy, new_galaxy_cluster, pythonify=True)

        # Publish the galaxy cluster
        source_instance.publish_galaxy_cluster(new_uuid)
        time.sleep(2)

        # Retrieve a cluster from the first available galaxy
        galaxies: list[MISPGalaxy] = source_instance.galaxies(pythonify=True)
        self.assertGreater(len(galaxies), 0, "No galaxy available")
        galaxy: MISPGalaxy = galaxies[-1]
        galaxy = source_instance.get_galaxy(galaxy.id, withCluster=True, pythonify=True)
        cluster: MISPGalaxyCluster = galaxy.clusters[0]

        # Attach the cluster as a local tag to the event
        source_instance.attach_galaxy_cluster(event, cluster, local=True)
        event = source_instance.get_event(event.id, pythonify=True)
        self.assertEqual(len(event.galaxies), 1)

        # Publish the event
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)

        # Pull on the target side
        purge_events_and_blocklists(target_instance)
        pull_result = misps_site_admin[target_index - 1].server_pull(server=server_id)
        time.sleep(2)
        check_response(pull_result)

        # Check
        results = target_instance.search(uuid=uuid)
        self.assertGreater(len(results), 0, f"Event not found on MISP_{target_index}")

        for result in results:
            galaxies = result['Event'].get('Galaxy', [])
            found = False
            for galaxy_data in galaxies:
                for cluster_data in galaxy_data.get('GalaxyCluster', []):
                    if str(cluster_data['uuid']) == str(cluster.uuid):
                        found = True
                        break
                if found:
                    break
            self.assertTrue(found, f"Local cluster {cluster.uuid} not found on MISP_{target_index}")

        # Cleanup: delete all test events on all instances
        for instance in misps_site_admin:
           purge_events_and_blocklists(instance)
        misps_site_admin[-1].delete_galaxy_cluster(cluster.uuid)
