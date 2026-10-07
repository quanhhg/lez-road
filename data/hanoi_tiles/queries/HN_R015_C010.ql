[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.203739,105.724508,21.249129,105.772918)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.203739,105.724508,21.249129,105.772918);
  node["barrier"](21.203739,105.724508,21.249129,105.772918);
);
(._; >>;);
out meta;
out count;
