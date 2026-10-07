[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.159886,105.339014,21.205169,105.387296)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.159886,105.339014,21.205169,105.387296);
  node["barrier"](21.159886,105.339014,21.205169,105.387296);
);
(._; >>;);
out meta;
out count;
