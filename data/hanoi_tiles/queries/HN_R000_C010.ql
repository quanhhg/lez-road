[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.526113,105.721268,20.571499,105.769453)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.526113,105.721268,20.571499,105.769453);
  node["barrier"](20.526113,105.721268,20.571499,105.769453);
);
(._; >>;);
out meta;
out count;
