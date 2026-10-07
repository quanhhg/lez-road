[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.661850,105.673907,20.707224,105.722123)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.661850,105.673907,20.707224,105.722123);
  node["barrier"](20.661850,105.673907,20.707224,105.722123);
);
(._; >>;);
out meta;
out count;
