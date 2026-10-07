[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.066953,105.964483,21.112408,106.012916)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.066953,105.964483,21.112408,106.012916);
  node["barrier"](21.066953,105.964483,21.112408,106.012916);
);
(._; >>;);
out meta;
out count;
