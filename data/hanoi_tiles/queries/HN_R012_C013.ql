[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.067500,105.868232,21.112929,105.916638)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.067500,105.868232,21.112929,105.916638);
  node["barrier"](21.067500,105.868232,21.112929,105.916638);
);
(._; >>;);
out meta;
out count;
