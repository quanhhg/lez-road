[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.932471,105.771281,20.977873,105.819614)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.932471,105.771281,20.977873,105.819614);
  node["barrier"](20.932471,105.771281,20.977873,105.819614);
);
(._; >>;);
out meta;
out count;
