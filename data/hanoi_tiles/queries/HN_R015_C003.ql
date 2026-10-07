[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.204945,105.387293,21.250241,105.435603)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.204945,105.387293,21.250241,105.435603);
  node["barrier"](21.204945,105.387293,21.250241,105.435603);
);
(._; >>;);
out meta;
out count;
