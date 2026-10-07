[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.977645,105.771513,21.023047,105.819861)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.977645,105.771513,21.023047,105.819861);
  node["barrier"](20.977645,105.771513,21.023047,105.819861);
);
(._; >>;);
out meta;
out count;
