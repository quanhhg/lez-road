[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.069285,105.435072,21.114595,105.483352)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.069285,105.435072,21.114595,105.483352);
  node["barrier"](21.069285,105.435072,21.114595,105.483352);
);
(._; >>;);
out meta;
out count;
