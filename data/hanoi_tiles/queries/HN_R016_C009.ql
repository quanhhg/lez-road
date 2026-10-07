[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.249126,105.676542,21.294503,105.724953)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.249126,105.676542,21.294503,105.724953);
  node["barrier"](21.249126,105.676542,21.294503,105.724953);
);
(._; >>;);
out meta;
out count;
