[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.204152,105.628163,21.249516,105.676545)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.204152,105.628163,21.249516,105.676545);
  node["barrier"](21.204152,105.628163,21.249516,105.676545);
);
(._; >>;);
out meta;
out count;
