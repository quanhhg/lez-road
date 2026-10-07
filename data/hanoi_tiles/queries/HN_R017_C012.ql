[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.293614,105.821352,21.339032,105.869820)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.293614,105.821352,21.339032,105.869820);
  node["barrier"](21.293614,105.821352,21.339032,105.869820);
);
(._; >>;);
out meta;
out count;
