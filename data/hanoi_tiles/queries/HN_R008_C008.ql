[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.887927,105.626838,20.933289,105.675115)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.887927,105.626838,20.933289,105.675115);
  node["barrier"](20.887927,105.626838,20.933289,105.675115);
);
(._; >>;);
out meta;
out count;
