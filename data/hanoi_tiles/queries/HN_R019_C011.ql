[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.384201,105.773625,21.429605,105.822110)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.384201,105.773625,21.429605,105.822110);
  node["barrier"](21.384201,105.773625,21.429605,105.822110);
);
(._; >>;);
out meta;
out count;
