[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.661643,105.721906,20.707030,105.770135)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.661643,105.721906,20.707030,105.770135);
  node["barrier"](20.661643,105.721906,20.707030,105.770135);
);
(._; >>;);
out meta;
out count;
