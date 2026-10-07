[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.160079,105.242692,21.205335,105.290945)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.160079,105.242692,21.205335,105.290945);
  node["barrier"](21.160079,105.242692,21.205335,105.290945);
);
(._; >>;);
out meta;
out count;
