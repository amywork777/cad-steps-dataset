"""
Onshape API client with convenience methods.
Python 3 port of onshape-public-apikey/python/apikey/client.py

Additional methods for CAD parsing from onshape-cad-parser/myclient.py
"""

from .onshape import Onshape

import mimetypes
import random
import string
import os


class Client:
    """
    Onshape API client with methods for documents, part studios, and CAD parsing.
    """

    def __init__(self, stack='https://cad.onshape.com', creds='./creds.json', logging=True):
        self._stack = stack
        self._api = Onshape(stack=stack, creds=creds, logging=logging)

    # ---- Document operations ----

    def new_document(self, name='Test Document', owner_type=0, public=False):
        payload = {'name': name, 'ownerType': owner_type, 'isPublic': public}
        return self._api.request('post', '/api/documents', body=payload)

    def rename_document(self, did, name):
        return self._api.request('post', '/api/documents/' + did, body={'name': name})

    def del_document(self, did):
        return self._api.request('delete', '/api/documents/' + did)

    def get_document(self, did):
        return self._api.request('get', '/api/documents/' + did)

    def list_documents(self):
        return self._api.request('get', '/api/documents')

    # ---- Part studio operations ----

    def get_features(self, did, wid, eid):
        """Gets the feature list for specified document / workspace / part studio."""
        return self._api.request('get', f'/api/partstudios/d/{did}/w/{wid}/e/{eid}/features')

    def get_tessellatedfaces(self, did, wid, eid):
        """Gets tessellated faces for specified document / workspace / part studio."""
        return self._api.request('get', f'/api/partstudios/d/{did}/w/{wid}/e/{eid}/tessellatedfaces')

    def get_partstudio_tessellatededges(self, did, wid, eid):
        return self._api.request('get', f'/api/partstudios/d/{did}/w/{wid}/e/{eid}/tessellatededges')

    def part_studio_stl(self, did, wid, eid):
        """Exports STL from a part studio."""
        req_headers = {'Accept': 'application/vnd.onshape.v1+octet-stream'}
        return self._api.request('get', f'/api/partstudios/d/{did}/w/{wid}/e/{eid}/stl',
                                 headers=req_headers)

    # ---- FeatureScript evaluation ----

    def get_entity_by_id(self, did, wid, eid, geo_id, entity_type):
        """Get geometry entity parameters by entity ID and type."""
        func_dict = {
            "VERTEX": ("evVertexPoint", "vertex"),
            "EDGE": ("evCurveDefinition", "edge"),
            "FACE": ("evSurfaceDefinition", "face")
        }
        body = {
            "script":
                "function(context is Context, queries) { "
                "   var res_list = [];"
                "   var q_arr = evaluateQuery(context, queries.id);"
                "   for (var i = 0; i < size(q_arr); i+= 1){"
                f"       var res = {func_dict[entity_type][0]}(context, {{\"{func_dict[entity_type][1]}\": q_arr[i]}});"
                "       res_list = append(res_list, res);"
                "   }"
                "   return res_list;"
                "}",
            "queries": [{"key": "id", "value": geo_id}]
        }
        return self._api.request('post', f'/api/partstudios/d/{did}/w/{wid}/e/{eid}/featurescript', body=body)

    def eval_boundingBox(self, did, wid, eid):
        """Get bounding box of all solid bodies."""
        body = {
            "script":
                "function(context is Context, queries) { "
                "   var q_body = qBodyType(qEverything(EntityType.BODY), BodyType.SOLID);"
                "   var bbox = evBox3d(context, {'topology': q_body});"
                "   return bbox;"
                "}",
            "queries": []
        }
        response = self._api.request('post', f'/api/partstudios/d/{did}/w/{wid}/e/{eid}/featurescript', body=body)
        bbox_values = response.json()['result']['message']['value']
        result = {}
        for item in bbox_values:
            k = item['message']['key']['message']['value']
            point_values = item['message']['value']['message']['value']
            v = [x['message']['value'] for x in point_values]
            result[k] = v
        return result

    def eval_curveLength(self, did, wid, eid, geo_id):
        """Get the length of a curve by entity ID."""
        body = {
            "script":
                "function(context is Context, queries) { "
                "   var res_list = [];"
                "   var q_arr = evaluateQuery(context, queries.id);"
                "   for (var i = 0; i < size(q_arr); i+= 1){"
                "       var res = evLength(context, {\"entities\": q_arr[i]});"
                "       res_list = append(res_list, res);"
                "   }"
                "   return res_list;"
                "}",
            "queries": [{"key": "id", "value": [geo_id]}]
        }
        response = self._api.request('post', f'/api/partstudios/d/{did}/w/{wid}/e/{eid}/featurescript', body=body)
        return response.json()['result']['message']['value'][0]['message']['value']

    def eval_curve_midpoint(self, did, wid, eid, geo_id):
        """Get the midpoint of a curve by entity ID."""
        body = {
            "script":
                "function(context is Context, queries) { "
                "   var q_arr = evaluateQuery(context, queries.id);"
                "   var midpoint = evEdgeTangentLine(context, {\"edge\": q_arr[0], \"parameter\": 0.5 }).origin;"
                "   return midpoint;"
                "}",
            "queries": [{"key": "id", "value": [geo_id]}]
        }
        response = self._api.request('post', f'/api/partstudios/d/{did}/w/{wid}/e/{eid}/featurescript', body=body)
        point_info = response.json()['result']['message']['value']
        return [x['message']['value'] for x in point_info]

    def expr2meter(self, did, wid, eid, expr):
        """Convert value expression to meter unit."""
        body = {
            "script":
                "function(context is Context, queries) { "
                f"   return lookupTableEvaluate(\"{expr}\") * meter;"
                "}",
            "queries": []
        }
        res = self._api.request('post', f'/api/partstudios/d/{did}/w/{wid}/e/{eid}/featurescript', body=body).json()
        return res['result']['message']['value']

    def eval_sketch_topology_by_adjacency(self, did, wid, eid, feat_id):
        """Parse hierarchical parametric geometry & topology from a sketch feature."""
        body = {
            "script":
                "function(context is Context, queries) { "
                "   var topo = {};"
                "   topo.faces = [];"
                "   topo.edges = [];"
                "   topo.vertices = [];"
                "   var all_edge_ids = [];"
                "   var all_vertex_ids = [];"
                f"   var q_face = qSketchRegion(makeId(\"{feat_id}\"));"
                "   var face_arr = evaluateQuery(context, q_face);"
                "   for (var i = 0; i < size(face_arr); i += 1) {"
                "       var face_topo = {};"
                "       const face_id = transientQueriesToStrings(face_arr[i]);"
                "       face_topo.id = face_id;"
                "       face_topo.edges = [];"
                "       face_topo.param = evSurfaceDefinition(context, {face: face_arr[i]});"
                "       var q_edge = qAdjacent(face_arr[i], AdjacencyType.EDGE, EntityType.EDGE);"
                "       var edge_arr = evaluateQuery(context, q_edge);"
                "       for (var j = 0; j < size(edge_arr); j += 1) {"
                "           var edge_topo = {};"
                "           const edge_id = transientQueriesToStrings(edge_arr[j]);"
                "           edge_topo.id = edge_id;"
                "           edge_topo.vertices = [];"
                "           edge_topo.param = evCurveDefinition(context, {edge: edge_arr[j]});"
                "           face_topo.edges = append(face_topo.edges, edge_id);"
                "           var q_vertex = qAdjacent(edge_arr[j], AdjacencyType.VERTEX, EntityType.VERTEX);"
                "           var vertex_arr = evaluateQuery(context, q_vertex);"
                "           for (var k = 0; k < size(vertex_arr); k += 1) {"
                "               var vertex_topo = {};"
                "               const vertex_id = transientQueriesToStrings(vertex_arr[k]);"
                "               vertex_topo.id = vertex_id;"
                "               vertex_topo.param = evVertexPoint(context, {vertex: vertex_arr[k]});"
                "               edge_topo.vertices = append(edge_topo.vertices, vertex_id);"
                "               if (isIn(vertex_id, all_vertex_ids)){continue;}"
                "               all_vertex_ids = append(all_vertex_ids, vertex_id);"
                "               topo.vertices = append(topo.vertices, vertex_topo);"
                "           }"
                "           if (isIn(edge_id, all_edge_ids)){continue;}"
                "           all_edge_ids = append(all_edge_ids, edge_id);"
                "           topo.edges = append(topo.edges, edge_topo);"
                "       }"
                "       topo.faces = append(topo.faces, face_topo);"
                "   }"
                "   return topo;"
                "}",
            "queries": []
        }
        res = self._api.request('post', f'/api/partstudios/d/{did}/w/{wid}/e/{eid}/featurescript', body=body)

        res_msg = res.json()['result']['message']['value']
        topo = {}
        for item in res_msg:
            item_msg = item['message']
            k_str = item_msg['key']['message']['value']
            v_item = item_msg['value']['message']['value']
            outer_list = []
            for item_x in v_item:
                v_item_x = item_x['message']['value']
                geo_dict = {}
                for item_y in v_item_x:
                    k = item_y['message']['key']['message']['value']
                    v_msg = item_y['message']['value']
                    if k == 'param':
                        if k_str == 'faces':
                            v = Client.parse_face_msg(v_msg)[0]
                        elif k_str == 'edges':
                            v = Client.parse_edge_msg(v_msg)[0]
                        elif k_str == 'vertices':
                            v = Client.parse_vertex_msg(v_msg)[0]
                        else:
                            raise ValueError(f"Unknown key: {k_str}")
                    elif isinstance(v_msg['message']['value'], list):
                        v = [a['message']['value'] for a in v_msg['message']['value']]
                    else:
                        v = v_msg['message']['value']
                    geo_dict[k] = v
                outer_list.append(geo_dict)
            topo[k_str] = outer_list
        return topo

    def eval_bodydetails(self, did, wid, eid):
        """Parse the B-rep representation as a dict."""
        res = self._api.request('get', f'/api/partstudios/d/{did}/w/{wid}/e/{eid}/bodydetails').json()
        for body in res['bodies']:
            all_face_ids = [face['id'] for face in body['faces']]
            face_entity = self.get_entity_by_id(did, wid, eid, all_face_ids, 'FACE')
            face_params = self.parse_face_msg(face_entity.json()['result']['message']['value'])
            for i, face in enumerate(body['faces']):
                if face_params[i]['type'] == 'Plane':
                    x_axis = face_params[i]['x']
                elif face_params[i]['type'] == '':
                    x_axis = []
                else:
                    x_axis = face_params[i]['coordSystem']['xAxis']
                    z_axis = face_params[i]['coordSystem']['zAxis']
                    face['surface']['z_axis'] = z_axis
                face['surface']['x_axis'] = x_axis
        return res

    # ---- Static parsers (ported from myclient.py) ----

    @staticmethod
    def parse_vertex_msg(response):
        """Parse vertex parameters from OnShape response data."""
        data = [response] if not isinstance(response, list) else response
        vertices = []
        for item in data:
            xyz_msg = item['message']['value']
            xyz_type = item['message']['typeTag']
            p = [round(msg['message']['value'], 8) for msg in xyz_msg]
            unit = xyz_msg[0]['message']['unitToPower'][0]
            unit_exp = (unit['key'], unit['value'])
            vertices.append({xyz_type: tuple(p), 'unit': unit_exp})
        return vertices

    @staticmethod
    def parse_coord_msg(response):
        """Parse coordSystem parameters from OnShape response data."""
        coord_param = {}
        for item in response:
            k = item['message']['key']['message']['value']
            v_msg = item['message']['value']
            v = [round(x['message']['value'], 8) for x in v_msg['message']['value']]
            coord_param[k] = v
        return coord_param

    @staticmethod
    def parse_edge_msg(response):
        """Parse edge parameters from OnShape response data."""
        data = [response] if not isinstance(response, list) else response
        edges = []
        for item in data:
            edge_msg = item['message']['value']
            edge_type = item['message']['typeTag']
            edge_param = {'type': edge_type}
            for msg in edge_msg:
                k = msg['message']['key']['message']['value']
                v_item = msg['message']['value']['message']['value']
                if k == 'coordSystem':
                    v = Client.parse_coord_msg(v_item)
                elif isinstance(v_item, list):
                    v = [round(x['message']['value'], 8) for x in v_item]
                else:
                    v = round(v_item, 8) if isinstance(v_item, float) else v_item
                edge_param[k] = v
            edges.append(edge_param)
        return edges

    @staticmethod
    def parse_face_msg(response):
        """Parse face parameters from OnShape response data."""
        data = [response] if not isinstance(response, list) else response
        faces = []
        for item in data:
            face_msg = item['message']['value']
            face_type = item['message']['typeTag']
            face_param = {'type': face_type}
            for msg in face_msg:
                k = msg['message']['key']['message']['value']
                v_item = msg['message']['value']['message']['value']
                if k == 'coordSystem':
                    v = Client.parse_coord_msg(v_item)
                elif isinstance(v_item, list):
                    v = [round(x['message']['value'], 8) for x in v_item]
                else:
                    v = round(v_item, 8) if isinstance(v_item, float) else v_item
                face_param[k] = v
            faces.append(face_param)
        return faces

    def eval_entityID_created_by_feature(self, did, wid, eid, feat_id, entity_type):
        """Get IDs of all geometry entities created by a given feature."""
        if entity_type not in ['VERTEX', 'EDGE', 'FACE', 'BODY']:
            raise ValueError(f"Got entity_type: {entity_type}")
        body = {
            "script":
                "function(context is Context, queries) { "
                "   return transientQueriesToStrings("
                "       evaluateQuery(context, "
                f"           qCreatedBy(makeId(\"{feat_id}\"), EntityType.{entity_type})"
                "       )"
                "   );"
                "}",
            "queries": []
        }
        res = self._api.request('post', f'/api/partstudios/d/{did}/w/{wid}/e/{eid}/featurescript', body=body)
        res_msg = res.json()['result']['message']['value']
        return [item['message']['value'] for item in res_msg]

    # ---- Rollback operations (NEW for CAD-Steps) ----

    def set_rollback_bar(self, did, wid, eid, index=-1):
        """
        Set the rollback bar position in a part studio.

        Uses the updateRollback API endpoint:
        POST /api/partstudios/d/{did}/w/{wid}/e/{eid}/features/rollback

        IMPORTANT: This requires WRITE access to the document. For public
        documents you don't own, you must first copy the document using
        copy_document().

        Args:
            - did (str): Document ID
            - wid (str): Workspace ID
            - eid (str): Element ID
            - index (int): Feature index to roll back to.
              0 = before all features (empty state)
              N = after the Nth feature
              -1 = end (all features visible)

        Returns:
            - requests.Response
        """
        body = {"rollbackIndex": index}
        return self._api.request(
            'post',
            f'/api/partstudios/d/{did}/w/{wid}/e/{eid}/features/rollback',
            body=body
        )

    def copy_document(self, did, wid, name=None, is_public=True):
        """
        Copy an Onshape document to the authenticated user's account.

        Uses: POST /api/documents/{did}/workspaces/{wid}/copy

        IMPORTANT: Free Onshape accounts can only create PUBLIC documents.
        Set is_public=True (default) to avoid 409 errors on free accounts.

        Args:
            - did (str): Source document ID
            - wid (str): Source workspace ID
            - name (str): Name for the new document (default: auto-generated)
            - is_public (bool): Whether the copy should be public (default: True)

        Returns:
            - dict: {'newDocumentId': str, 'newWorkspaceId': str, ...}
            - None: if copy failed
        """
        body = {'isPublic': is_public}
        if name:
            body['newName'] = name

        res = self._api.request(
            'post',
            f'/api/documents/{did}/workspaces/{wid}/copy',
            body=body
        )

        if res.status_code != 200:
            return None

        return res.json()

    def export_step(self, did, wid, eid):
        """
        Export STEP file from a part studio at its current rollback state.

        Uses the createPartStudioTranslation endpoint which respects the
        current rollback bar position.

        Args:
            - did (str): Document ID
            - wid (str): Workspace ID
            - eid (str): Element ID

        Returns:
            - dict: Translation response with 'id' field for status polling
            - None: if export failed
        """
        # Check if there are any parts at current state
        parts_res = self.get_parts(did, wid, eid)
        if parts_res.status_code != 200:
            return None
        try:
            parts = parts_res.json()
            if not parts:
                return None
        except Exception:
            return None

        # Request STEP translation (respects rollback bar position)
        body = {
            "formatName": "STEP",
            "storeInDocument": False
        }
        trans_res = self._api.request(
            'post',
            f'/api/partstudios/d/{did}/w/{wid}/e/{eid}/translations',
            body=body
        )

        if trans_res.status_code not in (200, 201):
            return None

        return trans_res.json()

    def get_translation_status(self, translation_id):
        """Check the status of a translation request."""
        return self._api.request('get', f'/api/translations/{translation_id}')

    def download_translated_document(self, did, doc_id):
        """Download a translated document by its external data ID."""
        req_headers = {
            'Accept': 'application/octet-stream'
        }
        return self._api.request(
            'get',
            f'/api/documents/d/{did}/externaldata/{doc_id}',
            headers=req_headers
        )

    def get_parts(self, did, wid, eid):
        """Get list of parts in a part studio."""
        return self._api.request('get', f'/api/parts/d/{did}/w/{wid}/e/{eid}')

    def get_elements(self, did, wid):
        """Get list of elements (tabs) in a document workspace."""
        return self._api.request('get', f'/api/documents/d/{did}/w/{wid}/elements')

    def delete_document(self, did):
        """Delete a document. Use to clean up copies after processing."""
        return self._api.request('delete', f'/api/documents/{did}')
