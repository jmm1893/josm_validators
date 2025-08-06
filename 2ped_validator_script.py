from javax.swing import JOptionPane
from org.openstreetmap.josm.data.osm import Way, Node, DataSet
from org.openstreetmap.josm.gui import MainApplication
from org.openstreetmap.josm.gui.layer import OsmDataLayer
from org.openstreetmap.josm.data.coor import LatLon
from java.lang import Math
# =========
# Constants - change values as needed
# =========

SQUARE_HALF_DIAGONAL = 0.00005  #modify to change square size
DISTANCE_THRESHOLD_METERS = 5 #modify to change neighboring features distance to validate
ROAD_TYPES = [
    "motorway", "trunk", "primary", "secondary", "tertiary",
    "unclassified", "residential", "motorway_link", "trunk_link",
    "primary_link", "secondary_link", "tertiary_link", "service", "cycleway"
]
# Tag for marker (set to None to use default)
SQUARE_TAG_KEY = None  # e.g., "building"
SQUARE_TAG_VALUE = None  # e.g., "yes"
# =========
# Helper Functions
# =========
def is_excluded_cycleway(way):
    return way.hasTag("highway", "cycleway") and way.hasTag("foot", "no")
def is_plus_intersection(node, node_neighbors):
    return len(node_neighbors.get(node, [])) >= 4
def is_valid_crossing_way(tags):
    if tags.get("highway") == "cycleway" and tags.get("foot") == "no":
        return False
    footway = tags.get("footway")
    highway = tags.get("highway")
    cycleway = tags.get("cycleway")
    foot = tags.get("foot")
    if footway == "crossing" and highway == "footway":
        return True
    if cycleway == "crossing" and highway == "cycleway" and foot in ("designated", "yes"):
        return True
    return False
def check_crossing_tags(way):
    if is_excluded_cycleway(way):
        return []
    tags = way.getKeys()
    issues = []
    if tags.get("highway") == "service":
        return issues
    crossing = tags.get("crossing")
    crossing_markings = tags.get("crossing:markings")
    crossing_signals = tags.get("crossing:signals")
    if tags.get("highway") == "cycleway" and not (way.hasKey("foot") or way.hasKey("footway")):
        return issues
    valid_crossing = is_valid_crossing_way(tags)
    if crossing == "unmarked":
        if not valid_crossing:
            issues.append("Inconsistent tags: crossing=unmarked, but tags are not valid for a crossing (missing or wrong highway/footway/cycleway/foot tags)")
        elif crossing_markings and crossing_markings != "no":
            issues.append("Markings present: crossing=unmarked, but crossing:markings is present and not 'no'")
    elif crossing == "marked":
        if not valid_crossing:
            issues.append("Inconsistent tags: crossing=marked, but tags are not valid for a crossing (missing or wrong highway/footway/cycleway/foot tags)")
        elif not crossing_markings:
            issues.append("Missing markings: crossing=marked, but missing crossing:markings tag")
    elif crossing == "uncontrolled":
        if not valid_crossing:
            issues.append("Inconsistent tags: crossing=uncontrolled, but tags are not valid for a crossing (missing or wrong highway/footway/cycleway/foot tags)")
        elif not crossing_markings:
            issues.append("Missing markings: crossing=uncontrolled, but missing crossing:markings tag")
    elif crossing == "traffic_signals":
        if not valid_crossing:
            issues.append("Inconsistent tags: crossing=traffic_signals, but tags are not valid for a crossing (missing or wrong highway/footway/cycleway/foot tags)")
        elif not crossing_markings:
            issues.append("Missing markings: crossing=traffic_signals, but missing crossing:markings tag")
        elif not crossing_signals:
            issues.append("Missing signals: crossing=traffic_signals, but missing crossing:signals tag")
    else:
        if valid_crossing and not crossing:
            issues.append("Potentially missing crossing tag: valid crossing way tags present but missing crossing=* tag")
    return issues
def node_is_on_cycleway(node, all_ways):
    for w in all_ways:
        if w in all_ways and is_excluded_cycleway(w):
            continue
        if node in w.getNodes() and w.hasTag("highway", "cycleway"):
            return True
    return False
def is_valid_crossing_parent_way(way):
    if is_excluded_cycleway(way):
        return False
    tags = way.getKeys()
    return is_valid_crossing_way(tags)
def check_crossing_tag_consistency(node, parent_ways, all_ways):
    issues = []
    node_crossing = node.get("crossing") if node.hasKey("crossing") else None
    node_markings = node.get("crossing:markings") if node.hasKey("crossing:markings") else None
    def is_no_or_missing(val):
        return val is None or val == "no"
    for way in parent_ways:
        if is_excluded_cycleway(way):
            continue
        if not is_valid_crossing_parent_way(way):
            continue
        way_crossing = way.get("crossing") if way.hasKey("crossing") else None
        way_markings = way.get("crossing:markings") if way.hasKey("crossing:markings") else None
        if (is_no_or_missing(node_markings) and is_no_or_missing(way_markings)):
            pass
        elif (node_markings == "yes" and way_markings != "yes") or (way_markings == "yes" and node_markings != "yes"):
            issues.append("crossing:markings=* mismatch or missing where one is 'yes'")
        elif node_markings and way_markings and node_markings != way_markings:
            issues.append("crossing:markings=* mismatch between node and way")
        elif (node_markings and not way_markings and node_markings != "no") or (way_markings and not node_markings and way_markings != "no"):
            issues.append("crossing:markings=* present on one but not the other")
        if node_crossing and way_crossing and node_crossing != way_crossing:
            issues.append("crossing=* mismatch between node and way")
        if (node_crossing and not way_crossing) or (way_crossing and not node_crossing):
            issues.append("crossing=* present on one but not the other")
    return issues
def check_crossing_tag_consistency_way(way):
    issues = []
    if is_excluded_cycleway(way):
        return issues
    if not is_valid_crossing_parent_way(way):
        return issues
    way_crossing = way.get("crossing") if way.hasKey("crossing") else None
    way_markings = way.get("crossing:markings") if way.hasKey("crossing:markings") else None
    def is_no_or_missing(val):
        return val is None or val == "no"
    for node in way.getNodes():
        if node.hasTag("highway", "crossing"):
            node_crossing = node.get("crossing") if node.hasKey("crossing") else None
            node_markings = node.get("crossing:markings") if node.hasKey("crossing:markings") else None
            if is_no_or_missing(node_markings) and is_no_or_missing(way_markings):
                pass
            elif (node_markings == "yes" and way_markings != "yes") or (way_markings == "yes" and node_markings != "yes"):
                issues.append((node, "crossing:markings=* mismatch or missing where one is 'yes'"))
            elif node_markings and way_markings and node_markings != way_markings:
                issues.append((node, "crossing:markings=* mismatch between way and node"))
            elif (node_markings and not way_markings and node_markings != "no") or (way_markings and not node_markings and way_markings != "no"):
                issues.append((node, "crossing:markings=* present on one but not the other"))
            if node_crossing and way_crossing and node_crossing != way_crossing:
                issues.append((node, "crossing=* mismatch between way and node"))
            if (node_crossing and not way_crossing) or (way_crossing and not node_crossing):
                issues.append((node, "crossing=* present on one but not the other"))
    return issues
def is_crossing_missing_tag(node, all_ways):
    if not node.hasTag("highway", "crossing"):
        return (False, "")
    if node.hasKey("crossing"):
        return (False, "")
    for way in all_ways:
        if is_excluded_cycleway(way):
            continue
        if node in way.getNodes():
            if way.hasTag("highway", "service"):
                return (False, "")
    return (True, "highway=crossing node is missing crossing=* tag (not on a service way)")
def create_marker_around(coor, dataset, note_text):
    lat = coor.lat()
    lon = coor.lon()
    delta = SQUARE_HALF_DIAGONAL / Math.sqrt(2)
    corners = [
        LatLon(lat + delta, lon - delta),
        LatLon(lat + delta, lon + delta),
        LatLon(lat - delta, lon + delta),
        LatLon(lat - delta, lon - delta)
    ]
    marker_nodes = []
    for corner in corners:
        node = Node(corner)
        dataset.addPrimitive(node)
        marker_nodes.append(node)
    marker_nodes.append(marker_nodes[0])
    marker_way = Way()
    marker_way.setNodes(marker_nodes)
    tag_key = SQUARE_TAG_KEY if SQUARE_TAG_KEY else "building"
    tag_value = SQUARE_TAG_VALUE if SQUARE_TAG_VALUE else "yes"
    marker_way.put(tag_key, tag_value)
    marker_way.put("note", note_text)
    dataset.addPrimitive(marker_way)
def remove_existing_layer(layer_name):
    layer_manager = MainApplication.getLayerManager()
    for layer in layer_manager.getLayers():
        if layer.getName() == layer_name:
            layer_manager.removeLayer(layer)
            break
# =========
# Main Logic
# =========
def main():
    edit_layer = MainApplication.getLayerManager().getEditLayer()
    if not edit_layer:
        JOptionPane.showMessageDialog(
            MainApplication.getMainFrame(),
            "No active data layer found."
        )
        return
    original_layer_name = edit_layer.getName()
    selected = edit_layer.data.getSelected()
    if not selected:
        JOptionPane.showMessageDialog(
            MainApplication.getMainFrame(),
            "No features selected."
        )
        return
    selected_ways = [w for w in selected if isinstance(w, Way)]
    if not selected_ways:
        JOptionPane.showMessageDialog(
            MainApplication.getMainFrame(),
            "No ways selected."
        )
        return
    selected_nodes = set()
    for way in selected_ways:
        selected_nodes.update(way.getNodes())
    all_relevant_ways = set(selected_ways)
    for way in edit_layer.data.getWays():
        if way in all_relevant_ways:
            continue
        if is_excluded_cycleway(way):
            continue
        for node in way.getNodes():
            for sel_node in selected_nodes:
                try:
                    if node.getCoor().greatCircleDistance(sel_node.getCoor()) <= DISTANCE_THRESHOLD_METERS:
                        all_relevant_ways.add(way)
                        break
                except Exception:
                    pass
            if way in all_relevant_ways:
                break
    footway_nodes = set()
    road_nodes = set()
    node_neighbors = {}
    for way in all_relevant_ways:
        if is_excluded_cycleway(way):
            continue
        nodes = way.getNodes()
        for i, node in enumerate(nodes):
            if node not in node_neighbors:
                node_neighbors[node] = set()
            if i > 0:
                node_neighbors[node].add(nodes[i - 1])
            if i < len(nodes) - 1:
                node_neighbors[node].add(nodes[i + 1])
            if way.hasTag("highway", "footway") or (
                way.hasTag("highway", "cycleway") and (way.hasTag("foot", "designated") or way.hasTag("foot", "yes"))
            ):
                footway_nodes.add(node)
            elif way.hasKey("highway") and way.get("highway") in ROAD_TYPES:
                road_nodes.add(node)
    shared_nodes = footway_nodes.intersection(road_nodes)
    # Remove existing "Footway Tag Checks" layer if it exists
    remove_existing_layer("Footway Tag Checks")
    # Create validation layer
    combined_data = DataSet()
    combined_layer = OsmDataLayer(combined_data, "Footway Tag Checks", None)
    # Draw markers shape for detected issues
    for node in shared_nodes:
        if is_plus_intersection(node, node_neighbors):
            if node.hasTag("highway", "crossing"):
                continue
            create_marker_around(
                node.getCoor(),
                combined_data,
                "Likely missing highway=crossing: Node at intersection of footway and road (plus intersection) has no crossing tag. [Untagged crossing detected]"
            )
    # 1. Check crossing tag logic errors on ways and include  description
    for way in all_relevant_ways:
        if is_excluded_cycleway(way):
            continue
        if way.hasTag("highway", "cycleway") and not (way.hasKey("foot") or way.hasKey("footway")):
            continue
        if way.hasTag("highway", "service"):
            continue
        crossing_issues = check_crossing_tags(way)
        if crossing_issues:
            midpoint_index = len(way.getNodes()) // 2
            midpoint_node = way.getNode(midpoint_index)
            create_marker_around(
                midpoint_node.getCoor(), 
                combined_data, 
                "Crossing tag logic problem(s): " + "; ".join(crossing_issues) + " [Way: id=%s]." % way.getId()
            )
    # 2. Node <-> way consistency: for all nodes with parent crossing ways
    for node in shared_nodes:
        node_highway_types = set()
        for way in all_relevant_ways:
            if is_excluded_cycleway(way):
                continue
            if node in way.getNodes() and way.hasKey("highway"):
                node_highway_types.add(way.get("highway"))
        if "footway" in node_highway_types and "service" in node_highway_types:
            if not node.hasTag("highway", "crossing"):
                create_marker_around(
                    node.getCoor(), combined_data,
                    "Missing highway=crossing: Node at intersection of footway and service road."
                )
            else:
                continue
        if is_plus_intersection(node, node_neighbors):
            parent_ways = [w for w in all_relevant_ways if node in w.getNodes() and is_valid_crossing_parent_way(w)]
            relevant_ways_for_check = [
                w for w in parent_ways if not (w.hasTag("highway", "cycleway") and not (w.hasKey("foot") or w.hasKey("footway")))
            ]
            if not relevant_ways_for_check:
                continue
            issues = check_crossing_tag_consistency(node, parent_ways, all_relevant_ways)
            if issues:
                create_marker_around(
                    node.getCoor(), 
                    combined_data, 
                    "Crossing tag mismatch at node: " + "; ".join(issues) + " [Node: id=%s]" % node.getId()
                )
    # 3. Way <-> node consistency: for each crossing way, check its crossing nodes
    for way in all_relevant_ways:
        if is_excluded_cycleway(way):
            continue
        if way.hasTag("highway", "cycleway") and not (way.hasKey("foot") or way.hasKey("footway")):
            continue
        if way.hasTag("highway", "service"):
            continue
        way_issues = check_crossing_tag_consistency_way(way)
        for node, issue in way_issues:
            if is_plus_intersection(node, node_neighbors):
                desc = "Crossing tag mismatch between way (id=%s) and node (id=%s): %s" % (way.getId(), node.getId(), issue)
                create_marker_around(
                    node.getCoor(),
                    combined_data,
                    desc
                )
    # 4. Missing crossing=* tag on highway=crossing nodes
    for way in all_relevant_ways:
        if is_excluded_cycleway(way):
            continue
        for node in way.getNodes():
            missing, desc = is_crossing_missing_tag(node, all_relevant_ways)
            if missing:
                create_marker_around(node.getCoor(), combined_data, "Tag issue: %s [Node id=%s]" % (desc, node.getId()))
    # Only add the combined_layer if there are actual primitives (markers) in combined_data.
    if combined_data.allPrimitives:
        MainApplication.getLayerManager().addLayer(combined_layer)
        JOptionPane.showMessageDialog(
            MainApplication.getMainFrame(),
            "Markers added for issues in selected and nearby features."
        )
    else:
        JOptionPane.showMessageDialog(
            MainApplication.getMainFrame(),
            "No issues detected"
        )
# =========
# Run the main function
# =========
if __name__ == "__main__":
    main()
