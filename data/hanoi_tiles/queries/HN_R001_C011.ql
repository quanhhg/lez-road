[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.571070,105.769450,20.616469,105.817664)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.571070,105.769450,20.616469,105.817664);
  node["barrier"](20.571070,105.769450,20.616469,105.817664);
);
(._; >>;);
out meta;
out count;
