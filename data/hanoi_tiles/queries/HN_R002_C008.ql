[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.616867,105.625722,20.662228,105.673910)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.616867,105.625722,20.662228,105.673910);
  node["barrier"](20.616867,105.625722,20.662228,105.673910);
);
(._; >>;);
out meta;
out count;
