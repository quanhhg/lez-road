[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.979062,105.386707,21.024358,105.434943)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.979062,105.386707,21.024358,105.434943);
  node["barrier"](20.979062,105.386707,21.024358,105.434943);
);
(._; >>;);
out meta;
out count;
