[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.705578,105.962177,20.751029,106.010490)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.705578,105.962177,20.751029,106.010490);
  node["barrier"](20.705578,105.962177,20.751029,106.010490);
);
(._; >>;);
out meta;
out count;
