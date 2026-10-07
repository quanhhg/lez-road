[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.750750,105.962463,20.796202,106.010790)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.750750,105.962463,20.796202,106.010790);
  node["barrier"](20.750750,105.962463,20.796202,106.010790);
);
(._; >>;);
out meta;
out count;
