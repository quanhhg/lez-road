[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.751994,105.722334,20.797382,105.770593)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.751994,105.722334,20.797382,105.770593);
  node["barrier"](20.751994,105.722334,20.797382,105.770593);
);
(._; >>;);
out meta;
out count;
