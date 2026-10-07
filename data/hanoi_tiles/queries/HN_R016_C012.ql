[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.248443,105.821101,21.293860,105.869554)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.248443,105.821101,21.293860,105.869554);
  node["barrier"](21.248443,105.821101,21.293860,105.869554);
);
(._; >>;);
out meta;
out count;
