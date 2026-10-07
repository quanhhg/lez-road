[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.978278,105.627214,21.023641,105.675521)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.978278,105.627214,21.023641,105.675521);
  node["barrier"](20.978278,105.627214,21.023641,105.675521);
);
(._; >>;);
out meta;
out count;
