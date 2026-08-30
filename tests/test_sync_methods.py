import unittest
import time
import uuid as UUID
from common import misps_site_admin, misps_org_admin, create_event, publish_immediately, request, check_response, get_servers_id, extract_server_numbers, find_unidirectional_link, purge_events_and_blocklists
from pymisp import PyMISP, MISPSighting, MISPNote, MISPGalaxy, MISPGalaxyCluster
from pymisp.api import get_uuid_or_id_from_abstract_misp

class TestSyncMethodsEnabled(unittest.TestCase):
    def testSyncSightingsOnPush(self):
        """
        Checks that sightings are properly synchronized when an event is pushed.
        """
        # Use the first MISP instance as the source
        source_instance = misps_org_admin[0]

        # Create an event and add an attribute
        event = create_event('Event for sightings sync on push')
        event.distribution = 2
        event = source_instance.add_event(event, pythonify=True)
        check_response(event)
        self.assertIsNotNone(event.id)
        uuid = event.uuid

        # Add a sighting to the first attribute
        attr_id = event.attributes[0].id
        sighting = MISPSighting()
        sighting.value = event.attributes[0].value
        sighting.source = 'SyncTest'
        sighting.type = '0'
        r = source_instance.add_sighting(sighting, event.attributes[0], pythonify=True)
        self.assertEqual(r.source, 'SyncTest')

        # Publish the event and push to linked servers
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)

        # Get the server configurations linked to this instance
        servers = misps_site_admin[0].servers()
        servers_id = get_servers_id(servers)
        if not servers_id:
            raise Exception("No server configuration found for the source instance")

        # Push the event to each linked server (a push all is needed for sightings)
        for server_id in servers_id:
            push_response = misps_site_admin[0].server_push(server=server_id)
            time.sleep(2)
            check_response(push_response)

        # Check for the presence of the sighting in the Sighting structure of each target instance
        linked_server_numbers = extract_server_numbers(servers)
        for target_index in linked_server_numbers:
            target_instance = misps_org_admin[target_index - 1]
            search_results = target_instance.search(uuid=uuid, include_sightings=True)
            self.assertGreater(len(search_results), 0, f"Event not found on MISP_{target_index} after push")
            event_data = search_results[0]['Event']
            found = False
            for attr in event_data.get('Attribute', []):
                if str(attr['id']) == str(attr_id) and 'Sighting' in attr:
                    for s in attr['Sighting']:
                        if s['source'] == 'SyncTest' and str(s['attribute_id']) == str(attr_id):
                            found = True
                            break
                if found:
                    break
            self.assertTrue(found, f"Sighting not found in Attribute/Sighting on MISP_{target_index} after push")

        # Cleanup: delete all test events on all instances
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)


    def testSyncSightingsOnPull(self):
        """
        Checks that sightings are properly synchronized when an event is pulled.
        """
        # Find a unidirectional link between two instances
        source_instance, target_instance, source_index, target_index, server_id = find_unidirectional_link()
        print(f"Unidirectional link: {source_index} --> {target_index}")

        # Create an event and add an attribute
        event = create_event('Event for sightings sync on pull')
        event.distribution = 2
        event = source_instance.add_event(event, pythonify=True)
        check_response(event)
        self.assertIsNotNone(event.id)
        uuid = event.uuid

        # Add a sighting to the first attribute
        attr_id = event.attributes[0].id
        sighting = MISPSighting()
        sighting.value = event.attributes[0].value
        sighting.source = 'SyncTest'
        sighting.type = '0'
        r = source_instance.add_sighting(sighting, event.attributes[0], pythonify=True)
        self.assertEqual(r.source, 'SyncTest')

        # Publish the event immediately
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)

        # Perform the pull on the target instance (a pull all is needed for sightings)
        pull_result = misps_site_admin[target_index - 1].server_pull(server=server_id)
        time.sleep(2)  # Allow time for pull to complete
        check_response(pull_result)

        # Check for the presence of the sighting in the Sighting structure of the target instance
        found = False
        results = target_instance.search(uuid=uuid, include_sightings=True)
        if results:
            found = False
            event_data = results[0]['Event']
            for attr in event_data.get('Attribute', []):
                if str(attr['id']) == str(attr_id) and 'Sighting' in attr:
                    for s in attr['Sighting']:
                        if s['source'] == 'SyncTest' and str(s['attribute_id']) == str(attr_id):
                            found = True
                            break
                if found:
                    break
        self.assertTrue(found, f"Sighting not found in Attribute/Sighting on MISP_{target_index} after pull")

        # Cleanup: delete all test events on all instances
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)


    def testSyncAnalystDataOnPush(self):
        """
        Checks that analyst data (notes) are properly synchronized when an event is pushed.
        """
        # Use the first MISP instance as the source
        source_instance = misps_org_admin[0]

        # Create an event and add a note as analyst data
        event = create_event('Event for analyst data sync on push')
        event.distribution = 2
        event = source_instance.add_event(event, pythonify=True)
        check_response(event)
        self.assertIsNotNone(event.id)
        uuid = event.uuid

        # Add a note linked to the event
        note = MISPNote()
        note.object_type = 'Event'
        note.object_uuid = uuid
        note.note = 'Test analyst note'
        note.distribution = 2
        note = source_instance.add_note(note, pythonify=True)
        self.assertEqual(note.object_uuid, uuid)
        self.assertEqual(note.object_type, 'Event')
        self.assertEqual(note.note, 'Test analyst note')

        # Publish the event and push to linked servers
        publish_immediately(source_instance, event, with_email=False)
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



        # Check if the analyst data is present in the target instance
        linked_server_numbers = extract_server_numbers(servers)
        for target_index in linked_server_numbers:
            target_instance = misps_org_admin[target_index - 1]

            # There is no Pymisp function allowing to fetch analyst data
            search_results = target_instance._check_response(target_instance._prepare_request(
                'GET',
                '/analystData/index/Note'
            ))
            #print(search_results)
            found = False
            if search_results:
                for note in search_results:
                    if note['Note']['object_uuid'] == uuid and note['Note']['note'] == 'Test analyst note':
                        found = True
                        break
            self.assertTrue(found, f"Analyst note not found on MISP_{target_index} after push")

        # Cleanup: delete all test events on all instances
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)


    def testSyncAnalystDataOnPull(self):
        """
        Checks that analyst data (notes) are properly synchronized when an event is pulled.
        """
        # Find a unidirectional link between two instances
        source_instance, target_instance, source_index, target_index, server_id = find_unidirectional_link()
        print(f"Unidirectional link: {source_index} --> {target_index}")

        # Create an event and add a note as analyst data
        event = create_event('Event for analyst data sync on pull')
        event.distribution = 2
        event = source_instance.add_event(event, pythonify=True)
        check_response(event)
        self.assertIsNotNone(event.id)
        uuid = event.uuid

        # Add a note linked to the event
        note = MISPNote()
        note.object_type = 'Event'
        note.object_uuid = uuid
        note.note = 'Test analyst note'
        note = source_instance.add_note(note, pythonify=True)
        self.assertEqual(note.object_uuid, uuid)
        self.assertEqual(note.object_type, 'Event')
        self.assertEqual(note.note, 'Test analyst note')

        # Publish the event immediately
        publish_immediately(source_instance, event, with_email=False)
        time.sleep(2)

        # Perform the pull on the target instance (pull all is needed for analyst data)
        pull_result = misps_site_admin[target_index - 1].server_pull(server=server_id)
        time.sleep(2)  # Allow time for pull to complete
        check_response(pull_result)

        # There is no Pymisp function allowing to fetch analyst data
        search_results = target_instance._check_response(target_instance._prepare_request(
            'GET',
            '/analystData/index/Note'
        ))
        #print(search_results)
        found = False
        if search_results:
            for note in search_results:
                if note['Note']['object_uuid'] == uuid and note['Note']['note'] == 'Test analyst note':
                    found = True
                    break
        self.assertTrue(found, f"Analyst note not found on MISP_{target_index} after pull")

        # Cleanup: delete all test events on all instances
        for instance in misps_site_admin:
            purge_events_and_blocklists(instance)


    def testSyncGalaxyClusterOnPush(self):
        """
        Checks that galaxy clusters are properly synchronized when pushed from the server index.
        """
        # Use the first MISP instance as the source
        source_instance = misps_org_admin[0]

        # Create a galaxy
        source_instance._check_response(source_instance._prepare_request(
            'POST',
            '/galaxies/add',
            data={
                'name': 'Galaxy for Push',
                'namespace': 'MISP Test',
                'distribution': 2,
                'description': 'testSyncGalaxyClusterOnPush'
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

        # Get the cluster ID
        cluster_id = get_uuid_or_id_from_abstract_misp(new_galaxy_cluster)
        print(f"Created cluster ID: {cluster_id}")

        # Publish the galaxy cluster
        source_instance.publish_galaxy_cluster(cluster_id)
        time.sleep(2)

        # Get the server configurations linked to this instance
        servers = misps_site_admin[0].servers()
        servers_id = get_servers_id(servers)
        if not servers_id:
            raise Exception("No server configuration found for the source instance")

        # Push the galaxy cluster to each linked server (a push all is needed for galaxy clusters)
        for server_id in servers_id:
            push_response = misps_site_admin[0].server_push(server=server_id)
            time.sleep(2)
            check_response(push_response)

        # Check for the presence of the galaxy cluster in all linked servers
        linked_server_numbers = extract_server_numbers(servers)
        for target_index in linked_server_numbers:
            target_instance = misps_site_admin[target_index - 1]

            # Fetch the galaxy on the target instance (with clusters included!)
            last_galaxy = target_instance.get_galaxy(new_galaxy, withCluster=True, pythonify=True)
            if last_galaxy:
                self.assertEqual(
                    last_galaxy.uuid,
                    new_galaxy.uuid,
                    f"Last galaxy on MISP_{target_index} is not the one we just published"
                )

            # Now fetch the clusters explicitly
            clusters = target_instance.search_galaxy_clusters(last_galaxy, pythonify=True)
            if not clusters:
                raise AssertionError(f"No clusters found in galaxy on MISP_{target_index}")

            last_cluster = clusters[-1]
            self.assertEqual(
                last_cluster.uuid,
                new_uuid,
                f"Last galaxy cluster on MISP_{target_index} is not the one we just published"
            )


    def testSyncGalaxyClusterOnPull(self):
        """
        Checks that galaxy clusters are properly synchronized when pulled from the server index.
        """
        # Find a unidirectional link between two instances
        source_instance, target_instance, source_index, target_index, server_id = find_unidirectional_link()
        print(f"Unidirectional link: {source_index} --> {target_index}")

        # Create a galaxy
        source_instance._check_response(source_instance._prepare_request(
            'POST',
            '/galaxies/add',
            data={
                'name': 'Galaxy for Pull',
                'namespace': 'MISP Test',
                'distribution': 2,
                'description': 'testSyncGalaxyClusterOnPull'
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

        # Get the cluster ID
        cluster_id = get_uuid_or_id_from_abstract_misp(new_galaxy_cluster)
        print(f"Created cluster ID: {cluster_id}")

        # Publish the galaxy cluster
        source_instance.publish_galaxy_cluster(cluster_id)
        time.sleep(2)


        # Perform the pull on the target instance
        pull_result = misps_site_admin[target_index - 1].server_pull(server=server_id)
        time.sleep(2)  # Allow time for pull to complete
        check_response(pull_result)

        # Check for the presence of the cluster
        last_galaxy = target_instance.get_galaxy(new_galaxy, withCluster=True, pythonify=True)
        if last_galaxy:
            self.assertEqual(
                last_galaxy.uuid,
                new_galaxy.uuid,
                f"Last galaxy on MISP_{target_index} is not the one we just published"
            )

        # Now fetch the clusters explicitly
        clusters = target_instance.search_galaxy_clusters(last_galaxy, pythonify=True)
        if not clusters:
            raise AssertionError(f"No clusters found in galaxy on MISP_{target_index}")

        last_cluster = clusters[-1]
        self.assertEqual(
            last_cluster.uuid,
            new_uuid,
            f"Last galaxy cluster on MISP_{target_index} is not the one we just published"
        )


