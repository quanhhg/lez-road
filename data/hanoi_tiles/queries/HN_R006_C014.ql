[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.796199,105.914710,20.841639,105.963039)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.796199,105.914710,20.841639,105.963039);
  node["barrier"](20.796199,105.914710,20.841639,105.963039);
);
(._; >>;);
out meta;
out count;
