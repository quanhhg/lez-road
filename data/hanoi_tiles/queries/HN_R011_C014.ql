[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.022062,105.916081,21.067503,105.964486)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.022062,105.916081,21.067503,105.964486);
  node["barrier"](21.022062,105.916081,21.067503,105.964486);
);
(._; >>;);
out meta;
out count;
