[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.067234,105.916358,21.112675,105.964777)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.067234,105.916358,21.112675,105.964777);
  node["barrier"](21.067234,105.916358,21.112675,105.964777);
);
(._; >>;);
out meta;
out count;
