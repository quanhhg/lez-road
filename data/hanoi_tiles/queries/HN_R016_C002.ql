[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.250238,105.339221,21.295521,105.387532)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.250238,105.339221,21.295521,105.387532);
  node["barrier"](21.250238,105.339221,21.295521,105.387532);
);
(._; >>;);
out meta;
out count;
