[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.660940,105.865900,20.706365,105.914170)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.660940,105.865900,20.706365,105.914170);
  node["barrier"](20.660940,105.865900,20.706365,105.914170);
);
(._; >>;);
out meta;
out count;
