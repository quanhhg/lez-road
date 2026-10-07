[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.979178,105.338605,21.024461,105.386827)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.979178,105.338605,21.024461,105.386827);
  node["barrier"](20.979178,105.338605,21.024461,105.386827);
);
(._; >>;);
out meta;
out count;
