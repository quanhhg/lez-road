[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.024458,105.290590,21.069727,105.338812)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.024458,105.290590,21.069727,105.338812);
  node["barrier"](21.024458,105.290590,21.069727,105.338812);
);
(._; >>;);
out meta;
out count;
