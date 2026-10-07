[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.205062,105.339117,21.250345,105.387414)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.205062,105.339117,21.250345,105.387414);
  node["barrier"](21.205062,105.339117,21.250345,105.387414);
);
(._; >>;);
out meta;
out count;
