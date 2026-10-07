[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.978081,105.675314,21.023456,105.723635)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.978081,105.675314,21.023456,105.723635);
  node["barrier"](20.978081,105.675314,21.023456,105.723635);
);
(._; >>;);
out meta;
out count;
