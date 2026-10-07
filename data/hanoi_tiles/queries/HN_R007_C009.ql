[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.842555,105.674708,20.887930,105.722983)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.842555,105.674708,20.887930,105.722983);
  node["barrier"](20.842555,105.674708,20.887930,105.722983);
);
(._; >>;);
out meta;
out count;
