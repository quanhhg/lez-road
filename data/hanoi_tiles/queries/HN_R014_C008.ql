[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.158978,105.627972,21.204341,105.676339)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.158978,105.627972,21.204341,105.676339);
  node["barrier"](21.158978,105.627972,21.204341,105.676339);
);
(._; >>;);
out meta;
out count;
