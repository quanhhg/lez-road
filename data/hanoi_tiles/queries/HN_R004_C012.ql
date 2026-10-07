[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.706362,105.818145,20.751775,105.866416)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.706362,105.818145,20.751775,105.866416);
  node["barrier"](20.706362,105.818145,20.751775,105.866416);
);
(._; >>;);
out meta;
out count;
