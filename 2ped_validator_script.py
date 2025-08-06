from javax.swing import JOptionPane
from org.openstreetmap.josm.data.osm import Way, Node, DataSet
from org.openstreetmap.josm.gui import MainApplication
from org.openstreetmap.josm.gui.layer import OsmDataLayer
from org.openstreetmap.josm.data.coor import LatLon
from java.lang import Math

# =========================
# Constants- change values as needed
# =========================

CIRCLE_NODE_COUNT = 12
RADIUS = 0.00005
SQUARE_HALF_DIAGONAL = 0.00005
DISTANCE_THRESHOLD_METERS = 5

ROAD_TYPES = [
  "motorway", "trunk", "primary", "secondary", "tertiary",
  "unclassified", "residential", "motorway_link", "trunk_link",
  "primary_link", "secondary_link", "tertiary_link", "service", "cycleway"
]

# =========================
# Helper Functions
# =========================

def is_excluded_cycleway(way):
    """
    Returns True if the way is highway=cycleway and foot=no.
    """
    return way.hasTag("highway", "cycleway") and way.hasTag("foot", "no")

def is_plus_intersection(node, node_neighbors):
    """
    Returns True if node has 4 or more neighbors, indicating a '+' intersection.
    """
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
    """
    Checks logic errors on crossing-related tags for a way.
    Returns a list of descriptive issue messages found.
    """
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
        # Problem: crossing is marked unmarked but tags/markings wrong
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
    """
    Returns True if the node is part of any way with highway=cycleway.
    """
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
    """
    Checks for crossing/crossing:markings mismatches between a node and its parent crossing ways.
    Returns a list of issues found.
    """
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

        # --- crossing:markings logic ---
        # If both are missing, or both are "no", or one is "no" and the other is missing, skip
        if (is_no_or_missing(node_markings) and is_no_or_missing(way_markings)):
            pass  # No issue
        # If either is "yes" and the other is not "yes", trigger
        elif (node_markings == "yes" and way_markings != "yes") or (way_markings == "yes" and node_markings != "yes"):
            issues.append("crossing:markings=* mismatch or missing where one is 'yes'")
        # If both are present and not equal (and not covered above), trigger
        elif node_markings and way_markings and node_markings != way_markings:
            issues.append("crossing:markings=* mismatch between node and way")
        # If one is present (not 'no') and the other is missing, trigger
        elif (node_markings and not way_markings and node_markings != "no") or (way_markings and not node_markings and way_markings != "no"):
            issues.append("crossing:markings=* present on one but not the other")

        # --- crossing logic (unchanged) ---
        if node_crossing and way_crossing and node_crossing != way_crossing:
            issues.append("crossing=* mismatch between node and way")
        if (node_crossing and not way_crossing) or (way_crossing and not node_crossing):
            issues.append("crossing=* present on one but not the other")

    return issues

def check_crossing_tag_consistency_way(way):
    """
    Checks for crossing/crossing:markings mismatches between a way and its crossing nodes.
    Returns a list of (node, issue) tuples.
    """
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

            # --- crossing:markings logic ---
            if is_no_or_missing(node_markings) and is_no_or_missing(way_markings):
                pass  # No issue
            elif (node_markings == "yes" and way_markings != "yes") or (way_markings == "yes" and node_markings != "yes"):
                issues.append((node, "crossing:markings=* mismatch or missing where one is 'yes'"))
            elif node_markings and way_markings and node_markings != way_markings:
                issues.append((node, "crossing:markings=* mismatch between way and node"))
            elif (node_markings and not way_markings and node_markings != "no") or (way_markings and not node_markings and way_markings != "no"):
                issues.append((node, "crossing:markings=* present on one but not the other"))

            # --- crossing logic (unchanged) ---
            if node_crossing and way_crossing and node_crossing != way_crossing:
                issues.append((node, "crossing=* mismatch between way and node"))
            if (node_crossing and not way_crossing) or (way_crossing and not node_crossing):
                issues.append((node, "crossing=* present on one but not the other"))

    return issues

def is_crossing_missing_tag(node, all_ways):
    """
    Checks if a highway=crossing node is missing a crossing=* tag (except if only on service).
    Returns a tuple (True/False, description) for use in note text.
    """
    if not node.hasTag("highway", "crossing"):
        return (False, "")
    if node.hasKey("crossing"):
        return (False, "")
    # if node only on service ways, ignore
    for way in all_ways:
        if is_excluded_cycleway(way):
            continue
        if node in way.getNodes():
            if way.hasTag("highway", "service"):
                return (False, "")
    return (True, "highway=crossing node is missing crossing=* tag (not on a service way)")

def create_square_around(coor, dataset, note_text):
    """
    Visual indicator: draw a square around coordinates, attach note with specific issue description.
    """
    lat = coor.lat()
    lon = coor.lon()
    delta = SQUARE_HALF_DIAGONAL / Math.sqrt(2)
    corners = [
        LatLon(lat + delta, lon - delta),
        LatLon(lat + delta, lon + delta),
        LatLon(lat - delta, lon + delta),
        LatLon(lat - delta, lon - delta)
    ]
    square_nodes = []
    for corner in corners:
        node = Node(corner)
        dataset.addPrimitive(node)
        square_nodes.append(node)
    square_nodes.append(square_nodes[0])
    square_way = Way()
    square_way.setNodes(square_nodes)
    square_way.put("building", "yes")
    square_way.put("note", note_text)
    dataset.addPrimitive(square_way)

def remove_existing_layer(layer_name):
    """
    Removes an existing layer with the specified name.
    """
    layer_manager = MainApplication.getLayerManager()
    for layer in layer_manager.getLayers():
        if layer.getName() == layer_name:
            layer_manager.removeLayer(layer)
            break

# =========================
# Main Logic
# =========================

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

    # Create combined dataset and layer
    combined_data = DataSet()
    combined_layer = OsmDataLayer(combined_data, "Footway Tag Checks", None)

    # Draw circles for likely untagged crossings, with detailed note
    for node in shared_nodes:
        if is_plus_intersection(node, node_neighbors):
            if node.hasTag("highway", "crossing"):
                continue
            circle_nodes = []
            lat = node.getCoor().lat()
            lon = node.getCoor().lon()
            for i in range(CIRCLE_NODE_COUNT):
                angle = 2 * Math.PI * i / CIRCLE_NODE_COUNT
                dx = RADIUS * Math.cos(angle)
                dy = RADIUS * Math.sin(angle)
                circle_node = Node()
                circle_node.setCoor(LatLon(lat + dy, lon + dx))
                combined_data.addPrimitive(circle_node)
                circle_nodes.append(circle_node)
            circle_nodes.append(circle_nodes[0])
            circle_way = Way()
            circle_way.setNodes(circle_nodes)
            circle_way.put("building", "yes")
            circle_way.put("note", "Likely missing highway=crossing: Node at intersection of footway and road (plus intersection) has no crossing tag. [Untagged crossing detected]")
            combined_data.addPrimitive(circle_way)

    # 1. Check crossing tag logic errors on ways and include detailed description
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
            create_square_around(
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
                create_square_around(
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
                create_square_around(
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
                create_square_around(
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
                create_square_around(node.getCoor(), combined_data, "Tag issue: %s [Node id=%s]" % (desc, node.getId()))

    # Only add the combined_layer if there are actual primitives (circles or squares) in combined_data.
    if combined_data.allPrimitives:
        MainApplication.getLayerManager().addLayer(combined_layer)
        JOptionPane.showMessageDialog(
            MainApplication.getMainFrame(),
            "Circles and squares added for issues in selected and nearby features."
        )
    else:
        JOptionPane.showMessageDialog(
            MainApplication.getMainFrame(),
            "No issues detected"
        )

# =========================
# Run the main function
# =========================

if __name__ == "__main__":
    main()
