[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.023638,105.579288,21.068987,105.627595)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.023638,105.579288,21.068987,105.627595);
  node["barrier"](21.023638,105.579288,21.068987,105.627595);
);
(._; >>;);
out meta;
out count;
