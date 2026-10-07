[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.706597,105.770132,20.751997,105.818390)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.706597,105.770132,20.751997,105.818390);
  node["barrier"](20.706597,105.770132,20.751997,105.818390);
);
(._; >>;);
out meta;
out count;
