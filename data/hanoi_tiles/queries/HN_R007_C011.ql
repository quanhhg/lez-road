[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.842122,105.770820,20.887523,105.819123)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.842122,105.770820,20.887523,105.819123);
  node["barrier"](20.842122,105.770820,20.887523,105.819123);
);
(._; >>;);
out meta;
out count;
