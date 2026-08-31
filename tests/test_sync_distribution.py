import unittest
import time
import uuid as UUID
from common import misps_site_admin, misps_org_admin, create_event, publish_immediately, check_response, get_servers_id, extract_server_numbers, find_unidirectional_link, purge_events_and_blocklists
from pymisp import MISPGalaxy, MISPGalaxyCluster, MISPNote


class TestDistributionLevel(unittest.TestCase):
    def testEventDistributionLevelOnPush(self):
        """
        Explicitly tests the impact of the event distribution level on push synchronization between MISP instances.

        Distribution levels:
        0 - Your organisation only: The event must NOT be pushed to any other instance.
        1 - This community only: The event must NOT be pushed to any other instance.
        2 - Connected communities: The event MUST be pushed to instances in connected communities.
        3 - All communities: The event MUST be pushed to all instances.

        The test creates an event, changes its distribution level step by step, pushes it, and verifies its presence or absence on target instances according to the distribution level.
        """
        # Use the first MISP instance as source
        source_instance = misps_org_admin[0]

        # Create an event with distribution level 0 (Your organisation only)
        event = create_event('Event for distribution level 1')
        event.distribution = 0

        event = source_instance.add_event(event, pythonify=True)
        check_response(event)
        self.assertIsNotNone(event.id)
        uuid = event.uuid
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)  # Give time for sync propagation

        # Get the server configurations linked to this instance
        servers = misps_site_admin[0].servers()
        servers_id = get_servers_id(servers)
        if not servers_id:
            raise Exception("No server configuration found for the source instance")

        # Push the event to each linked server (before publication)
        for server_id in servers_id:
            push_response = misps_site_admin[0].server_push(server=server_id, event=event.id)
            time.sleep(2)  # Allow time for push to complete
            check_response(push_response)

        # Verify that the event is NOT present on any target instances
        linked_server_numbers = extract_server_numbers(servers)
        for target_index in linked_server_numbers:
            target_instance = misps_org_admin[target_index - 1]
            search_results = target_instance.search(uuid=uuid)
            self.assertEqual(
                len(search_results), 0,
                f"Event unexpectedly found on MISP_{target_index} with distribution level 0"
            )

        # Now change the distribution level to 1 (This community only)
        event.distribution = 1
        event = source_instance.update_event(event, pythonify=True)
        check_response(event)
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)  # Give time for sync propagation

        # Push the updated event to each linked server
        for server_id in servers_id:
            push_response = misps_site_admin[0].server_push(server=server_id, event=event.id)
            time.sleep(2)  # Allow time for push to complete
            check_response(push_response)

        # Verify that the event is still NOT present on any target instances
        for target_index in linked_server_numbers:
            target_instance = misps_org_admin[target_index - 1]
            search_results = target_instance.search(uuid=uuid)
            self.assertEqual(
                len(search_results), 0,
                f"Event unexpectedly found on MISP_{target_index} with distribution level 1"
            )

        # Change the distribution level to 2 (Connected communities)
        event.distribution = 2
        event = source_instance.update_event(event, pythonify=True)
        check_response(event)
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)  # Give time for sync propagation

        # Push the updated event to each linked server
        for server_id in servers_id:
            push_response = misps_site_admin[0].server_push(server=server_id, event=event.id)
            time.sleep(2)  # Allow time for push to complete
            check_response(push_response)

        # Verify that the event is present on all target instances in connected communities
        for target_index in linked_server_numbers:
            target_instance = misps_org_admin[target_index - 1]
            search_results = target_instance.search(uuid=uuid)
            self.assertGreater(
                len(search_results), 0,
                f"Event not found on MISP_{target_index} with distribution level 2"
            )

        # Change the distribution level to 3 (All communities)
        event.distribution = 3
        event = source_instance.update_event(event, pythonify=True)
        check_response(event)
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)  # Give time for sync propagation

        # Verify presence on all reachable instances
        for index, target_instance in enumerate(misps_org_admin, start=1):
            search_results = target_instance.search(uuid=uuid)
            self.assertGreater(
                len(search_results), 0,
                f"Event not found on MISP_{index} with distribution level 3"
            )
        # Cleanup: delete all test events on all instances
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)

    def testEventDistributionLevelOnPull(self):
        """
        Explicitly tests the impact of the event distribution level on pull synchronization between MISP instances.

        Distribution levels:
        0 - Your organisation only: The event must NOT be pulled by any other instance.
        1 - This community only: The event CAN be pulled by another instance.
        2 - Connected communities: The event MUST be pulled by instances in connected communities.
        3 - All communities: The event MUST be pulled by all instances.

        The test creates an event, changes its distribution level step by step, pulls it, and verifies its presence or absence on target instances according to the distribution level.
        """
        source_instance, target_instance, source_index, target_index, server_id = find_unidirectional_link()
        print(f"Pulling from MISP_{source_index} on MISP_{target_index}")

        # Create and publish an event on the source
        event = create_event('Event for distribution level')
        event.distribution = 0

        event = source_instance.add_event(event, pythonify=True)
        check_response(event)
        self.assertIsNotNone(event.id)
        uuid = event.uuid
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)  # Give time for sync propagation

        # Perform the pull on the target
        pull_result = misps_site_admin[target_index - 1].server_pull(server=server_id)
        time.sleep(5)  # Allow time for pull to complete
        check_response(pull_result)

        # Confirm the event exist on the target with distribution level 0
        found = False
        results = misps_site_admin[target_index - 1].search(uuid=uuid)  # Need to search on the misps_site_admin because the Your organisation only is related to the organisation of the user who can pull e.g. the site admin
        if results:
            found = True

        self.assertTrue(found, f"Event not found on MISP_{target_index} after pull and publication.")

        # Now change the distribution level to 1 (This community only)
        event.distribution = 1
        event = source_instance.update_event(event, pythonify=True)
        check_response(event)
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)  # Give time for sync propagation

        # Perform the pull again
        pull_result = misps_site_admin[target_index - 1].server_pull(server=server_id)
        check_response(pull_result)
        time.sleep(5)  # Allow time for pull to complete

        # Confirm the event now exists on the target
        results = misps_site_admin[target_index - 1].search(uuid=uuid)
        found = False
        if results:
            found = True
        self.assertTrue(found, f"Event not found on MISP_{target_index} after pull and publication.")

        # Now change the distribution level to 2 (Connected communities)
        event.distribution = 2
        event = source_instance.update_event(event, pythonify=True)
        check_response(event)
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)  # Give time for sync propagation

        # Perform the pull again
        pull_result = misps_site_admin[target_index - 1].server_pull(server=server_id)
        check_response(pull_result)
        time.sleep(5)  # Allow time for pull to complete

        # Confirm the event now exists on the target
        results = target_instance.search(uuid=uuid)
        found = False
        if results:
            found = True
        self.assertTrue(found, f"Event not found on MISP_{target_index} after pull and publication.")

        # Now change the distribution level to 3 (All communities)
        event.distribution = 3
        event = source_instance.update_event(event, pythonify=True)
        check_response(event)
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)  # Give time for sync propagation

        # Perform the pull again
        pull_result = misps_site_admin[target_index - 1].server_pull(server=server_id)
        check_response(pull_result)
        time.sleep(5)  # Allow time for pull to complete

        # Verify presence on all reachable instances
        for index, target_instance in enumerate(misps_org_admin, start=1):
            search_results = target_instance.search(uuid=uuid)
            self.assertGreater(
                len(search_results), 0,
                f"Event not found on MISP_{index} with distribution level 3"
            )

        # Cleanup: delete all test events on all instances
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)

    def testEventDowngradeDistributionLevelOnPush(self):
        """ 
        Explicitly tests the impact of push synchronization on the downgrade of event distribution level.

        Scenarios:
        - If an event is pushed with distribution level 2 (Connected communities), it MUST be present on all target instances with distribution level 1 (This community only).
        - If the event is then updated to distribution level 3 (All communities), it MUST be present on all target instances with distribution level 3.

        The test creates an event, pushes it, checks the downgrade, updates the event, pushes again, and verifies the new distribution level.
        """
        # Use the first MISP instance as source
        source_instance = misps_org_admin[0]

        # Create an event with distribution level 2 (Connected communities)
        event = create_event('Event for downgrade distribution level')
        event.distribution = 2

        event = source_instance.add_event(event, pythonify=True)
        check_response(event)
        self.assertIsNotNone(event.id)
        uuid = event.uuid
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)  # Give time for sync propagation

        # Get the server configurations linked to this instance
        servers = misps_site_admin[0].servers()
        servers_id = get_servers_id(servers)
        if not servers_id:
            raise Exception("No server configuration found for the source instance")

        # Push the event to each linked server (before publication)
        for server_id in servers_id:
            push_response = misps_site_admin[0].server_push(server=server_id, event=event.id)
            time.sleep(2)  # Allow time for push to complete
            check_response(push_response)

        # Verify that the event is present on all target instances in connected communities with distribution level 1
        linked_server_numbers = extract_server_numbers(servers)
        for target_index in linked_server_numbers:
            target_instance = misps_org_admin[target_index - 1]
            search_results = target_instance.search(uuid=uuid)
            # Check if the event is present with distribution level 1
            self.assertGreater(
                len(search_results), 0,
                f"Event not found on MISP_{target_index} with distribution level 1"
            )
            for result in search_results:
                self.assertEqual(int(result['Event']['distribution']), 1,
                                 f"Event on MISP_{target_index} has incorrect distribution level {result['Event']['distribution']}")

        # Now change the distribution level to 3 (All communities)
        event.distribution = 3
        event = source_instance.update_event(event, pythonify=True)
        check_response(event)
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)

        # Push the updated event to each linked server
        for server_id in servers_id:
            push_response = misps_site_admin[0].server_push(server=server_id, event=event.id)
            time.sleep(2)  # Allow time for push to complete
            check_response(push_response)

        # Verify that the event is still present on all target instances in connected communities with distribution level 3
        for target_index in linked_server_numbers:
            target_instance = misps_org_admin[target_index - 1]
            search_results = target_instance.search(uuid=uuid)
            self.assertGreater(
                len(search_results), 0,
                f"Event not found on MISP_{target_index} after pushing with distribution level 3"
            )
            for result in search_results:
                self.assertEqual(int(result['Event']['distribution']), 3,
                                 f"Event on MISP_{target_index} has incorrect distribution level {result['Event']['distribution']}")
                
        # Cleanup: delete all test events on all instances
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)

    def testEventDowngradeDistributionLevelOnPull(self):
        """ 
        Explicitly tests the impact of pull synchronization on the downgrade of event distribution level.

        Scenarios:
        - If an event is pulled with distribution level 1 (This community only), it MUST be present on all target instances with distribution level 0 (Your organisation only).
        - If an event is pulled with distribution level 2 (Connected communities), it MUST be present on all target instances with distribution level 1 (This community only).
        - If the event is then updated to distribution level 3 (All communities), it MUST be present on all target instances with distribution level 3.

        The test creates an event, pulls it, checks the downgrade, updates the event, pulls again, and verifies the new distribution level.
        """
        source_instance, target_instance, source_index, target_index, server_id = find_unidirectional_link()
        print(f"Pulling from MISP_{source_index} on MISP_{target_index}")

        # Create and publish an event on the source
        event_name = f"Event {source_index} for pull on {target_index} on downgrade distribution level"
        event = create_event(event_name)
        event.distribution = 1

        event = source_instance.add_event(event, pythonify=True)
        check_response(event)
        self.assertIsNotNone(event.id)
        uuid = event.uuid
        # Publish the event immediately
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2) # Give time for sync propagation

        # Perform the pull on the target
        pull_result = misps_site_admin[target_index - 1].server_pull(server=server_id, event=event.id)
        time.sleep(5)
        check_response(pull_result)

        # Confirm the event exists on the target with distribution level 0
        found = False
        results = misps_site_admin[target_index - 1].search(uuid=uuid) # Need to search on the misps_site_admin because the Your organisation only is related to the organisation of the user who can pull e.g. the site admin
        if results:
            found = True
            for result in results:
                self.assertEqual(int(result['Event']['distribution']), 0,
                                    f"Event on MISP_{target_index} has incorrect distribution level {result['Event']['distribution']}")

        self.assertTrue(found, f"Event not found on MISP_{target_index} after pull with distribution level 0.")

        # Now change the distribution level to 2 (Connected communities)
        event.distribution = 2
        event = source_instance.update_event(event, pythonify=True)
        check_response(event)
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)  # Give time for sync propagation

        # Perform the pull again to get the updated event
        pull_result = misps_site_admin[target_index - 1].server_pull(server=server_id, event=event.id)
        time.sleep(5)
        check_response(pull_result)
        # Confirm the event now exists on the target with distribution level 1
        results = target_instance.search(uuid=uuid)
        found = False
        if results:
            found = True
            for result in results:
                self.assertEqual(int(result['Event']['distribution']), 1,
                                    f"Event on MISP_{target_index} has incorrect distribution level {result['Event']['distribution']}")

        self.assertTrue(found, f"Event not found on MISP_{target_index} after pull with distribution level 2.")

        # Now change the distribution level to 3 (All communities)
        event.distribution = 3
        event = source_instance.update_event(event, pythonify=True)
        check_response(event)
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)  # Give time for sync propagation

        # Perform the pull again to get the updated event
        pull_result = misps_site_admin[target_index - 1].server_pull(server=server_id, event=event.id)
        time.sleep(5)
        check_response(pull_result)

        # Confirm the event now exists on the target with distribution level 3
        results = target_instance.search(uuid=uuid)
        found = False
        if results:
            found = True
            for result in results:
                self.assertEqual(int(result['Event']['distribution']), 3,
                                    f"Event on MISP_{target_index} has incorrect distribution level {result['Event']['distribution']}")

        self.assertTrue(found, f"Event not found on MISP_{target_index} after pull with distribution level 3.")

        # Cleanup: delete all test events on all instances
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)


    def testGalaxyDistributionLevelOnPush(self):
        """
        Test the distribution rules of galaxies and clusters when pushed across servers.
        - Iterate over galaxy distribution levels 0,1,2,3
        - For each galaxy, create 4 clusters with distribution levels 0,1,2,3
        - Publish clusters
        - Verify propagation rules:
            * Galaxy dist=0 or 1: no clusters visible remotely
            * Galaxy dist=2 or 3: only clusters dist=2 and 3 propagate
        """
        source_instance = misps_org_admin[0]

        # Loop over galaxy distribution levels
        for galaxy_dist in range(4):
            galaxy_name = f"Galaxy Dist {galaxy_dist} on Push"
            print(f"\n=== Testing Galaxy distribution level {galaxy_dist} ===")

            # Create galaxy with the given distribution
            source_instance._check_response(source_instance._prepare_request(
                'POST',
                '/galaxies/add',
                data={
                    'name': galaxy_name,
                    'namespace': 'MISP Test',
                    'distribution': galaxy_dist,
                    'description': f'Testing galaxy distribution level {galaxy_dist}'
                }
            ))
            new_galaxy = source_instance.galaxies(pythonify=True)[-1]

            # Create 4 clusters with distribution levels 0,1,2,3
            cluster_uuids = {}
            for cluster_dist in range(4):
                cluster_uuid = str(UUID.uuid4())
                cluster = MISPGalaxyCluster()
                cluster.uuid = cluster_uuid
                cluster.value = f"Cluster Dist {cluster_dist} for Galaxy {galaxy_dist}"
                cluster.authors = ["CIRCL"]
                cluster.distribution = cluster_dist
                cluster.description = f"Cluster with distribution {cluster_dist}"
                source_instance.add_galaxy_cluster(new_galaxy, cluster, pythonify=True)

                # Publish cluster
                source_instance.publish_galaxy_cluster(cluster.uuid)
                cluster_uuids[cluster_dist] = cluster.uuid

            time.sleep(2)  # allow sync

            # Get servers connected to source
            servers = misps_site_admin[0].servers()
            servers_id = get_servers_id(servers)
            if not servers_id:
                raise Exception("No server configuration found for the source instance")

            linked_server_numbers = extract_server_numbers(servers)

            # Check propagation on each target server
            for target_index in linked_server_numbers:
                target_instance = misps_site_admin[target_index - 1]
                # Retrieve galaxy with its clusters
                target_galaxy = target_instance.get_galaxy(new_galaxy, withCluster=True, pythonify=True)

                # For galaxies with dist 0 or 1, the galaxy itself should not be visible
                if galaxy_dist in (0, 1):
                    self.assertTrue(isinstance(target_galaxy, dict) and "errors" in target_galaxy, f"Galaxy should NOT propagate for galaxy dist {galaxy_dist}, but found {target_galaxy}")
                elif galaxy_dist in (2, 3):
                    self.assertIsNotNone(target_galaxy, f"Galaxy should propagate for galaxy dist {galaxy_dist}, but found None")
                    clusters = target_instance.search_galaxy_clusters(target_galaxy, pythonify=True)
                    found_uuids = {c.uuid for c in clusters} if clusters else set()
                    # Only clusters dist 2 and 3 must propagate
                    self.assertNotIn(cluster_uuids[0], found_uuids, f"Cluster dist 0 (uuid={cluster_uuids[0]}) should NOT propagate for galaxy dist {galaxy_dist}")
                    self.assertNotIn(cluster_uuids[1], found_uuids, f"Cluster dist 1 (uuid={cluster_uuids[1]}) should NOT propagate for galaxy dist {galaxy_dist}")
                    self.assertIn(cluster_uuids[2], found_uuids, f"Cluster dist 2 (uuid={cluster_uuids[2]}) should propagate for galaxy dist {galaxy_dist}")
                    self.assertIn(cluster_uuids[3], found_uuids, f"Cluster dist 3 (uuid={cluster_uuids[3]}) should propagate for galaxy dist {galaxy_dist}")


    def testGalaxyDistributionLevelOnPull(self):
        """
        Test the distribution rules of galaxies and clusters when pushed across servers.
        - Iterate over galaxy distribution levels 0,1,2,3
        - For each galaxy, create 4 clusters with distribution levels 0,1,2,3
        - Publish clusters
        - Verify propagation rules:
            * Galaxy dist=0 : no clusters visible remotely
            * Galaxy dist=1 : only clusters dist=1, dist=2 and 3 propagate
            * Galaxy dist=2 or 3: only clusters dist=2 and 3 propagate
        """
        # Find unidirectional link
        source_instance, target_instance, source_index, target_index, server_id = find_unidirectional_link()
        print(f"Pulling from MISP_{source_index} on MISP_{target_index}")

        # Loop over galaxy distribution levels
        for galaxy_dist in range(4):
            galaxy_name = f"Galaxy Dist {galaxy_dist} on Pull"
            print(f"\n=== Testing Galaxy distribution level {galaxy_dist} ===")

            # Create galaxy with the given distribution
            source_instance._check_response(source_instance._prepare_request(
                'POST',
                '/galaxies/add',
                data={
                    'name': galaxy_name,
                    'namespace': 'MISP Test',
                    'distribution': galaxy_dist,
                    'description': f'Testing galaxy distribution level {galaxy_dist}'
                }
            ))
            new_galaxy = source_instance.galaxies(pythonify=True)[-1]

            # Create 4 clusters with distribution levels 0,1,2,3
            cluster_uuids = {}
            for cluster_dist in range(4):
                cluster_uuid = str(UUID.uuid4())
                cluster = MISPGalaxyCluster()
                cluster.uuid = cluster_uuid
                cluster.value = f"Cluster Dist {cluster_dist} for Galaxy {galaxy_dist}"
                cluster.authors = ["CIRCL"]
                cluster.distribution = cluster_dist
                cluster.description = f"Cluster with distribution {cluster_dist}"
                source_instance.add_galaxy_cluster(new_galaxy, cluster, pythonify=True)

                # Publish cluster
                source_instance.publish_galaxy_cluster(cluster.uuid)
                cluster_uuids[cluster_dist] = cluster.uuid

            time.sleep(2)  # allow sync

            # Perform the pull on the target
            pull_result = misps_site_admin[target_index - 1].server_pull(server=server_id)
            time.sleep(5)  # Allow time for pull to complete
            check_response(pull_result)

            # Retrieve galaxy with its clusters
            target_galaxy = target_instance.get_galaxy(new_galaxy, withCluster=True, pythonify=True)

            # For galaxies with dist 0 or 1, the galaxy itself should not be visible
            if galaxy_dist == 0:
                self.assertTrue(isinstance(target_galaxy, dict) and "errors" in target_galaxy, f"Galaxy should NOT propagate for galaxy dist {galaxy_dist}, but found {target_galaxy}")
            elif galaxy_dist == 1:
                self.assertIsNotNone(target_galaxy, f"Galaxy should propagate for galaxy dist {galaxy_dist}, but found None")
                clusters = misps_site_admin[target_index - 1].search_galaxy_clusters(target_galaxy, pythonify=True)
                found_uuids = {c.uuid for c in clusters} if clusters else set()
                self.assertNotIn(cluster_uuids[0], found_uuids, f"Cluster dist 0 (uuid={cluster_uuids[0]}) should NOT propagate for galaxy with dist {galaxy_dist}")
                self.assertIn(cluster_uuids[1], found_uuids, f"Cluster dist 1 (uuid={cluster_uuids[1]}) should propagate for galaxy with dist {galaxy_dist}")
                self.assertIn(cluster_uuids[2], found_uuids, f"Cluster dist 2 (uuid={cluster_uuids[2]}) should propagate for galaxy with dist {galaxy_dist}")
                self.assertIn(cluster_uuids[3], found_uuids, f"Cluster dist 3 (uuid={cluster_uuids[3]}) should propagate for galaxy with dist {galaxy_dist}")
            elif galaxy_dist in (2, 3):
                self.assertIsNotNone(target_galaxy, f"Galaxy should propagate for galaxy dist {galaxy_dist}, but found None")
                clusters = misps_site_admin[target_index - 1].search_galaxy_clusters(target_galaxy, pythonify=True)
                found_uuids = {c.uuid for c in clusters} if clusters else set()
                # Only clusters dist 2 and 3 must propagate
                self.assertNotIn(cluster_uuids[0], found_uuids, f"Cluster dist 0 (uuid={cluster_uuids[0]}) should NOT propagate for galaxy with dist {galaxy_dist}")
                self.assertNotIn(cluster_uuids[1], found_uuids, f"Cluster dist 1 (uuid={cluster_uuids[1]}) should NOT propagate for galaxy with dist {galaxy_dist}")
                self.assertIn(cluster_uuids[2], found_uuids, f"Cluster dist 2 (uuid={cluster_uuids[2]}) should propagate for galaxy with dist {galaxy_dist}")
                self.assertIn(cluster_uuids[3], found_uuids, f"Cluster dist 3 (uuid={cluster_uuids[3]}) should propagate for galaxy with dist {galaxy_dist}")


    def testGalaxyDowngradeDistributionLevelOnPush(self):
        """
        Test downgrading of galaxy distribution level when pushed:
        - Galaxy dist=2 -> Galaxy should downgrade to dist=1 on remote servers
        - Galaxy dist=3 -> Galaxy should remain dist=3 on remote servers
        """
        source_instance = misps_org_admin[0]

        for galaxy_dist in [2, 3]:
            galaxy_name = f"Galaxy Dist {galaxy_dist} with Cluster Dist 2"
            print(f"\n=== Testing downgrade for Galaxy distribution {galaxy_dist} ===")

            # Create galaxy
            source_instance._check_response(source_instance._prepare_request(
                'POST',
                '/galaxies/add',
                data={
                    'name': galaxy_name,
                    'namespace': 'MISP Test',
                    'distribution': galaxy_dist,
                    'description': f'Test downgrade of galaxy dist {galaxy_dist}'
                }
            ))
            new_galaxy = source_instance.galaxies(pythonify=True)[-1]

            # Create cluster with distribution=2
            cluster_uuid = str(UUID.uuid4())
            cluster = MISPGalaxyCluster()
            cluster.uuid = cluster_uuid
            cluster.value = f"Cluster Dist 2 for Galaxy {galaxy_dist}"
            cluster.authors = ["CIRCL"]
            cluster.distribution = 2
            cluster.description = "Cluster with distribution 2"

            source_instance.add_galaxy_cluster(new_galaxy, cluster, pythonify=True)
            source_instance.publish_galaxy_cluster(cluster.uuid)

            time.sleep(2)  # allow sync

            # Get servers connected to source
            servers = misps_site_admin[0].servers()
            servers_id = get_servers_id(servers)
            if not servers_id:
                raise Exception("No server configuration found for the source instance")

            linked_server_numbers = extract_server_numbers(servers)

            # Check galaxy distribution on remote instances
            for target_index in linked_server_numbers:
                target_instance = misps_site_admin[target_index - 1]

                # Retrieve galaxy on target
                target_galaxy = target_instance.get_galaxy(new_galaxy, pythonify=True)

                print(f"On MISP_{target_index}, Galaxy {target_galaxy.uuid} has dist={target_galaxy.distribution}")

                if galaxy_dist == 2:
                    # Expect downgrade to dist=1
                    self.assertEqual(
                        target_galaxy.distribution,
                        1,
                        f"Galaxy dist 2 with cluster dist 2 should downgrade to dist 1 on MISP_{target_index}"
                    )
                elif galaxy_dist == 3:
                    # Expect galaxy stays at dist=3
                    self.assertEqual(
                        target_galaxy.distribution,
                        3,
                        f"Galaxy dist 3 with cluster dist 2 should remain dist 3 on MISP_{target_index}"
                    )


    def testGalaxyDowngradeDistributionLevelOnPull(self):
        """
        Test downgrading of galaxy distribution level when pulled:
        - Galaxy dist=1 -> Galaxy should remain dist=0 on remote servers
        - Galaxy dist=2 -> Galaxy should downgrade to dist=1 on remote servers
        - Galaxy dist=3 -> Galaxy should remain dist=3 on remote servers
        """
        # Find unidirectional link
        source_instance, target_instance, source_index, target_index, server_id = find_unidirectional_link()
        print(f"Pulling from MISP_{source_index} on MISP_{target_index}")

        for galaxy_dist in [1, 2, 3]:
            galaxy_name = f"Galaxy Dist {galaxy_dist} for Pull Downgrade"
            print(f"\n=== Testing downgrade for Galaxy distribution {galaxy_dist} ===")

            # Create galaxy
            source_instance._check_response(source_instance._prepare_request(
                'POST',
                '/galaxies/add',
                data={
                    'name': galaxy_name,
                    'namespace': 'MISP Test',
                    'distribution': galaxy_dist,
                    'description': f'Test downgrade of galaxy dist {galaxy_dist}'
                }
            ))
            new_galaxy = source_instance.galaxies(pythonify=True)[-1]

            # Create cluster with distribution=2
            cluster_uuid = str(UUID.uuid4())
            cluster = MISPGalaxyCluster()
            cluster.uuid = cluster_uuid
            cluster.value = f"Cluster Dist 2 for Galaxy {galaxy_dist}"
            cluster.authors = ["CIRCL"]
            cluster.distribution = 2
            cluster.description = "Cluster with distribution 2"
            source_instance.add_galaxy_cluster(new_galaxy, cluster, pythonify=True)
            source_instance.publish_galaxy_cluster(cluster.uuid)

            time.sleep(2)  # allow sync

            # Perform the pull on the target
            pull_result = misps_site_admin[target_index - 1].server_pull(server=server_id)
            time.sleep(5)  # Allow time for pull to complete
            check_response(pull_result)

            # Retrieve galaxy on target
            target_galaxy = target_instance.get_galaxy(new_galaxy, pythonify=True)
            print(f"On MISP_{target_index}, Galaxy {getattr(target_galaxy, 'uuid', None)} has dist={getattr(target_galaxy, 'distribution', None)}")

            if galaxy_dist == 1:
                # Should downgrade to dist=0
                self.assertEqual(
                    target_galaxy.distribution,
                    0,
                    f"Galaxy dist 1 should downgrade to dist 0 on MISP_{target_index}"
                )
            elif galaxy_dist == 2:
                # Should downgrade to dist=1
                self.assertEqual(
                    target_galaxy.distribution,
                    1,
                    f"Galaxy dist 2 should downgrade to dist 1 on MISP_{target_index}"
                )
            elif galaxy_dist == 3:
                # Should remain dist=3
                self.assertEqual(
                    target_galaxy.distribution,
                    3,
                    f"Galaxy dist 3 should remain dist 3 on MISP_{target_index}"
                )



    def testGalaxyClusterDowngradeDistributionOnPush(self):
        """
        Test downgrading galaxy cluster distribution level on push
        - Cluster dist=2 -> Cluster should downgrade to dist=1 on remote servers
        - Cluster dist=3 -> Cluster should remain dist=3 on remote servers
        """
        # Use the first MISP instance as source
        source_instance = misps_org_admin[0]

        # Create a galaxy (not implemented in PyMisp)
        source_instance._check_response(source_instance._prepare_request(
            'POST',
            '/galaxies/add',
            data={
                'name': 'Galaxy for Push',
                'namespace': 'MISP Test',
                'distribution': 2,
                'description': 'testGalaxyClusterDowngradeDistributionOnPush'
            }
        ))
        new_galaxy = source_instance.galaxies(pythonify=True)[-1]

        # Create a galaxy cluster with distribution 2
        first_uuid = str(UUID.uuid4())
        first_galaxy_cluster: MISPGalaxyCluster = MISPGalaxyCluster()
        first_galaxy_cluster.uuid = first_uuid
        first_galaxy_cluster.value = "Cluster for Push"
        first_galaxy_cluster.authors = ["CIRCL"]
        first_galaxy_cluster.distribution = 2
        first_galaxy_cluster.description = "A cluster description"
        source_instance.add_galaxy_cluster(new_galaxy, first_galaxy_cluster, pythonify=True)

        # Publish the galaxy cluster
        source_instance.publish_galaxy_cluster(first_uuid)
        time.sleep(2)

        # Create a galaxy cluster with distribution 3
        second_uuid = str(UUID.uuid4())
        second_galaxy_cluster: MISPGalaxyCluster = MISPGalaxyCluster()
        second_galaxy_cluster.uuid = second_uuid
        second_galaxy_cluster.value = "Cluster for Push"
        second_galaxy_cluster.authors = ["CIRCL"]
        second_galaxy_cluster.distribution = 3
        second_galaxy_cluster.description = "A cluster description"
        source_instance.add_galaxy_cluster(new_galaxy, second_galaxy_cluster, pythonify=True)

        # Publish the galaxy cluster
        source_instance.publish_galaxy_cluster(second_uuid)
        time.sleep(2)

        # Get the server configurations linked to this instance
        servers = misps_site_admin[0].servers()
        servers_id = get_servers_id(servers)
        if not servers_id:
            raise Exception("No server configuration found for the source instance")

        # Check for the presence of the galaxy cluster in all linked servers
        linked_server_numbers = extract_server_numbers(servers)
        for target_index in linked_server_numbers:
            target_instance = misps_site_admin[target_index -1]
            target_galaxy = target_instance.get_galaxy(new_galaxy, pythonify=True)
            clusters = target_instance.search_galaxy_clusters(target_galaxy, pythonify=True)
            first_cluster = next((c for c in clusters if c.uuid == first_uuid), None)
            second_cluster = next((c for c in clusters if c.uuid == second_uuid), None)

            if first_galaxy_cluster.distribution == 2:
                # Should downgrade to dist=1
                self.assertEqual(
                    first_cluster.distribution,
                    1,
                    f"Galaxy cluster dist 2 should downgrade to dist 1 on MISP_{target_index}"
                )
            elif second_galaxy_cluster.distribution == 3:
                # Should remain dist=3
                self.assertEqual(
                    second_cluster.distribution,
                    3,
                    f"Galaxy cluster dist 3 should remain dist 3 on MISP_{target_index}"
               )

    def testGalaxyClusterDowngradeDistributionOnPull(self):
        """
        Test downgrading galaxy cluster distribution level on pull
        - Cluster dist=1 -> Cluster should downgrade to dist=0 on remote servers
        - Cluster dist=2 -> Cluster should downgrade to dist=1 on remote servers
        - Cluster dist=3 -> Cluster should remain dist=3 on remote servers
        """
        # Find unidirectional link
        source_instance, target_instance, source_index, target_index, server_id = find_unidirectional_link()
        print(f"Pulling from MISP_{source_index} on MISP_{target_index}")

        # Create a galaxy (not implemented in PyMisp)
        source_instance._check_response(source_instance._prepare_request(
            'POST',
            '/galaxies/add',
            data={
                'name': 'Galaxy for Pull',
                'namespace': 'MISP Test',
                'distribution': 2,
                'description': 'testGalaxyClusterDowngradeDistributionOnPull'
            }
        ))
        new_galaxy = source_instance.galaxies(pythonify=True)[-1]

        # Create a galaxy cluster with distribution 1
        first_uuid = str(UUID.uuid4())
        first_galaxy_cluster: MISPGalaxyCluster = MISPGalaxyCluster()
        first_galaxy_cluster.uuid = first_uuid
        first_galaxy_cluster.value = "Cluster for Pull"
        first_galaxy_cluster.authors = ["CIRCL"]
        first_galaxy_cluster.distribution = 1
        first_galaxy_cluster.description = "A cluster description"
        source_instance.add_galaxy_cluster(new_galaxy, first_galaxy_cluster, pythonify=True)

        # Publish the galaxy cluster
        source_instance.publish_galaxy_cluster(first_uuid)
        time.sleep(2)

        # Create a galaxy cluster with distribution 2
        second_uuid = str(UUID.uuid4())
        second_galaxy_cluster: MISPGalaxyCluster = MISPGalaxyCluster()
        second_galaxy_cluster.uuid = second_uuid
        second_galaxy_cluster.value = "Cluster for Pull"
        second_galaxy_cluster.authors = ["CIRCL"]
        second_galaxy_cluster.distribution = 2
        second_galaxy_cluster.description = "A cluster description"
        source_instance.add_galaxy_cluster(new_galaxy, second_galaxy_cluster, pythonify=True)

        # Publish the galaxy cluster
        source_instance.publish_galaxy_cluster(second_uuid)
        time.sleep(2)

        # Create a galaxy cluster with distribution 3
        third_uuid = str(UUID.uuid4())
        third_galaxy_cluster: MISPGalaxyCluster = MISPGalaxyCluster()
        third_galaxy_cluster.uuid = third_uuid
        third_galaxy_cluster.value = "Cluster for Pull"
        third_galaxy_cluster.authors = ["CIRCL"]
        third_galaxy_cluster.distribution = 3
        third_galaxy_cluster.description = "A cluster description"
        source_instance.add_galaxy_cluster(new_galaxy, third_galaxy_cluster, pythonify=True)

        # Publish the galaxy cluster
        source_instance.publish_galaxy_cluster(third_uuid)
        time.sleep(2)

        # Perform the pull on the target
        pull_result = misps_site_admin[target_index - 1].server_pull(server=server_id)
        time.sleep(5)  # Allow time for pull to complete
        check_response(pull_result)

        # Retrieve galaxy and clusters on the target
        target_galaxy = target_instance.get_galaxy(new_galaxy, withCluster=True, pythonify=True)
        clusters = misps_site_admin[target_index - 1].search_galaxy_clusters(target_galaxy, pythonify=True)

        # Find clusters by uuid
        first_cluster = next((c for c in clusters if c.uuid == first_uuid), None)
        second_cluster = next((c for c in clusters if c.uuid == second_uuid), None)
        third_cluster = next((c for c in clusters if c.uuid == third_uuid), None)

        # Cluster dist=1 should downgrade to dist=0
        self.assertIsNotNone(first_cluster, "Cluster with dist=1 not found on target after pull")
        self.assertEqual(
            first_cluster.distribution,
            0,
            f"Galaxy cluster dist 1 should downgrade to dist 0 on MISP_{target_index}"
        )
        # Cluster dist=2 should downgrade to dist=1
        self.assertIsNotNone(second_cluster, "Cluster with dist=2 not found on target after pull")
        self.assertEqual(
            second_cluster.distribution,
            1,
            f"Galaxy cluster dist 2 should downgrade to dist 1 on MISP_{target_index}"
        )
        # Cluster dist=3 should remain dist=3
        self.assertIsNotNone(third_cluster, "Cluster with dist=3 not found on target after pull")
        self.assertEqual(
            third_cluster.distribution,
            3,
            f"Galaxy cluster dist 3 should remain dist 3 on MISP_{target_index}"
       )


    def testAnalystDataDistributionLevelOnPush(self):
        """
        Creates an event with distribution=3, adds 4 analyst data (dist 0 to 3),
        publishes the event, pushes it, then checks the propagation of the analyst data according to their distribution.
        """

        source_instance = misps_org_admin[0]

        # Create an event with distribution 3
        event = create_event('Event for analyst data distribution')
        event.distribution = 3
        event = source_instance.add_event(event, pythonify=True)
        check_response(event)
        self.assertIsNotNone(event.id)
        uuid = event.uuid

        # Create 4 analyst data (MISPNote) with distribution 0 to 3
        notes = []
        for dist in range(4):
            note = MISPNote()
            note.object_type = 'Event'
            note.object_uuid = event.uuid
            note.note = f"Some analyst content dist {dist}"
            note.distribution = dist
            added = source_instance.add_analyst_data(note, pythonify=True)
            check_response(added)
            notes.append(note)

        # Publish the event (which also publishes the analyst data)
        publish_immediately(source_instance, event, with_email=True)
        time.sleep(2)

        # Get the server configurations linked to this instance
        servers = misps_site_admin[0].servers()
        servers_id = get_servers_id(servers)
        if not servers_id:
            raise Exception("No server configuration found for the source instance")

        # Push the event to each linked server (a push all is needed for analyst data)
        for server_id in servers_id:
            push_response = misps_site_admin[0].server_push(server=server_id)
            time.sleep(2)
            check_response(push_response)

        # Verify on the target server
        linked_server_numbers = extract_server_numbers(servers)
        if not linked_server_numbers:
            raise Exception("No linked server found")
        target_index = linked_server_numbers[0]
        target_instance = misps_site_admin[target_index - 1]
        # Chercher l'event sur le serveur cible
        search_results = target_instance.search(uuid=uuid)
        self.assertGreater(len(search_results), 0, "Event not found on target instance")


        # Fetch  analyst data from the target server via get_analyst_data
        analyst_data_dist = [
            element.note
            for element in notes
            if target_instance.get_analyst_data(element, pythonify=True) is not None
        ]

        # Verify that dist 0 and 1 are not present, dist 2 and 3 are
        self.assertNotIn("Some analyst content dist 0", analyst_data_dist, "Analyst data dist 0 should NOT be present on target")
        self.assertNotIn("Some analyst content dist 1", analyst_data_dist, "Analyst data dist 1 should NOT be present on target")
        self.assertIn("Some analyst content dist 2", analyst_data_dist, "Analyst data dist 2 should be present on target")
        self.assertIn("Some analyst content dist 3", analyst_data_dist, "Analyst data dist 3 should be present on target")

        # If the target server has servers of its own, check for level 3 propagation
        servers2 = misps_site_admin[target_index - 1].servers()
        servers2_id = get_servers_id(servers2)
        if servers2_id:
            linked2 = extract_server_numbers(servers2)
            target2_index = linked2[0]
            target2_instance = misps_org_admin[target2_index - 1]
            search2 = target2_instance.search(uuid=uuid)
            self.assertGreater(len(search2), 0, "Event not found on second-level target")

            analyst_data_dist2 = [
                element.note
                for element in notes
                if target2_instance.get_analyst_data(element, pythonify=True) is not None
            ]

            self.assertNotIn("Some analyst content dist 0", analyst_data_dist2, "Analyst data dist 0 should NOT be present on second-level target")
            self.assertNotIn("Some analyst content dist 1", analyst_data_dist2, "Analyst data dist 1 should NOT be present on second-level target")
            self.assertNotIn("Some analyst content dist 2", analyst_data_dist2, "Analyst data dist 2 should NOT be present on second-level target")
            self.assertIn("Some analyst content dist 3", analyst_data_dist2, "Analyst data dist 3 should be present on second-level target")

        # Cleanup
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)



    def testAnalystDataDistributionLevelOnPull(self):
        source_instance, target_instance, source_index, target_index, server_id = find_unidirectional_link()
        print(f"Pulling Analyst Data from MISP_{source_index} on MISP_{target_index}")

        # Create an event with distribution 3 on the source
        event = create_event('Event for analyst data pull')
        event.distribution = 3
        event = source_instance.add_event(event, pythonify=True)
        check_response(event)
        self.assertIsNotNone(event.id)
        uuid = event.uuid

        # Create 4 analyst data (MISPNote) with distribution 0 to 3
        notes = []
        for dist in range(4):
            note = MISPNote()
            note.object_type = 'Event'
            note.object_uuid = event.uuid
            note.note = f"Some analyst content dist {dist}"
            note.distribution = dist
            added = source_instance.add_analyst_data(note, pythonify=True)
            check_response(added)
            notes.append(note)

        # Publish the event and the analyst data
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)

        # Pull on the target (a pull all is needed for analayst data)
        pull_result = misps_site_admin[target_index - 1].server_pull(server=server_id)
        time.sleep(5)
        check_response(pull_result)

        # Verify that the event is present on the target
        search_results = target_instance.search(uuid=uuid)
        self.assertGreater(len(search_results), 0, f"Event not found on MISP_{target_index} after pull")

        analyst_data_dist = [
            element.note
            for element in notes
            if target_instance.get_analyst_data(element, pythonify=True) is not None
        ]

        # Expected results
        self.assertNotIn("Some analyst content dist 0", analyst_data_dist, "Analyst data dist 0 should NOT be present on target")
        self.assertIn("Some analyst content dist 1", analyst_data_dist, "Analyst data dist 1 should be present on target")
        self.assertIn("Some analyst content dist 2", analyst_data_dist, "Analyst data dist 2 should be present on target")
        self.assertIn("Some analyst content dist 3", analyst_data_dist, "Analyst data dist 3 should be present on target")

        # Cleanup
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)


    
    def testAnalystDataDowngradeDistributionLevelOnPush(self):
        """
        Test the downgrade of the analyst data distribution during a push.
        - Analyst data dist=2 must be downgraded to dist=1 on the targets.
        - Analyst data dist=3 must remain dist=3 on the targets.
        """
        source_instance = misps_org_admin[0]

        # Create an event dist=3
        event = create_event('Event for analyst data downgrade push')
        event.distribution = 3
        event = source_instance.add_event(event, pythonify=True)
        check_response(event)
        uuid = event.uuid
        self.assertIsNotNone(event.id)

        # Add analyst data dist=2 and dist=3
        notes = []
        for dist in [2, 3]:
            note = MISPNote()
            note.object_type = 'Event'
            note.object_uuid = event.uuid
            note.note = f"Analyst data push dist {dist}"
            note.distribution = dist
            added = source_instance.add_analyst_data(note, pythonify=True)
            check_response(added)
            notes.append(note)

        # Publish the event and the analyst data
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)

        # Push to all linked servers (a push all is needed for analyst data)
        servers = misps_site_admin[0].servers()
        servers_id = get_servers_id(servers)
        for server_id in servers_id:
            push_response = misps_site_admin[0].server_push(server=server_id)
            time.sleep(2)
            check_response(push_response)

        # Verify downgrade on the targets
        linked_server_numbers = extract_server_numbers(servers)
        for target_index in linked_server_numbers:
            target_instance = misps_site_admin[target_index - 1]
            for note in notes:
                target_note = target_instance.get_analyst_data(note, pythonify=True)
                self.assertIsNotNone(target_note, f"Analyst data dist {note.distribution} not found on MISP_{target_index}")
                if note.distribution == 2:
                    self.assertEqual(int(target_note.distribution), 1,
                                    f"Analyst data dist 2 should downgrade to dist 1 on MISP_{target_index}")
                elif note.distribution == 3:
                    self.assertEqual(int(target_note.distribution), 3,
                                    f"Analyst data dist 3 should remain dist 3 on MISP_{target_index}")

        # Cleanup
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)



    def testAnalystDataDowngradeDistributionLevelOnPull(self):
        """
        Tests the downgrade of the analyst data distribution during a pull.
        - Analyst data dist=1 must be downgraded to dist=0
        - Analyst data dist=2 must be downgraded to dist=1
        - Analyst data dist=3 must remain at dist=3
        """
        source_instance, target_instance, source_index, target_index, server_id = find_unidirectional_link()
        print(f"Pulling Analyst Data from MISP_{source_index} on MISP_{target_index}")

        # Create an event dist=3
        event = create_event(f"Event {source_index} for analyst data downgrade pull")
        event.distribution = 3
        event = source_instance.add_event(event, pythonify=True)
        check_response(event)
        uuid = event.uuid
        self.assertIsNotNone(event.id)

        # Add analyst data dist=1, 2, 3
        notes = []
        for dist in [1, 2, 3]:
            note = MISPNote()
            note.object_type = 'Event'
            note.object_uuid = event.uuid
            note.note = f"Analyst data pull dist {dist}"
            note.distribution = dist
            added = source_instance.add_analyst_data(note, pythonify=True)
            check_response(added)
            notes.append(note)

        # Publish the event and the analyst data
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)

        # Pull on the target (a pull all is needed for analyst data)
        pull_result = misps_site_admin[target_index - 1].server_pull(server=server_id)
        time.sleep(5)
        check_response(pull_result)

        # Verify downgrade on the target
        for note in notes:
            target_note = target_instance.get_analyst_data(note, pythonify=True)
            self.assertIsNotNone(target_note, f"Analyst data dist {note.distribution} not found on MISP_{target_index}")
            if note.distribution == 1:
                self.assertEqual(int(target_note.distribution), 0,
                                f"Analyst data dist 1 should downgrade to dist 0 on MISP_{target_index}")
            elif note.distribution == 2:
                self.assertEqual(int(target_note.distribution), 1,
                                f"Analyst data dist 2 should downgrade to dist 1 on MISP_{target_index}")
            elif note.distribution == 3:
                self.assertEqual(int(target_note.distribution), 3,
                                f"Analyst data dist 3 should remain dist 3 on MISP_{target_index}")

        # Cleanup
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)


