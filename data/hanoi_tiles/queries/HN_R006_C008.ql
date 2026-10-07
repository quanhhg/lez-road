[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.797575,105.626464,20.842936,105.674711)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.797575,105.626464,20.842936,105.674711);
  node["barrier"](20.797575,105.626464,20.842936,105.674711);
);
(._; >>;);
out meta;
out count;
