[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.204338,105.579990,21.249688,105.628358)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.204338,105.579990,21.249688,105.628358);
  node["barrier"](21.204338,105.579990,21.249688,105.628358);
);
(._; >>;);
out meta;
out count;
