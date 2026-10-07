[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.616673,105.673708,20.662047,105.721909)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.616673,105.673708,20.662047,105.721909);
  node["barrier"](20.616673,105.673708,20.662047,105.721909);
);
(._; >>;);
out meta;
out count;
