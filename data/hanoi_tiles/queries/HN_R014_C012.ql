[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.158098,105.820602,21.203515,105.869024)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.158098,105.820602,21.203515,105.869024);
  node["barrier"](21.158098,105.820602,21.203515,105.869024);
);
(._; >>;);
out meta;
out count;
