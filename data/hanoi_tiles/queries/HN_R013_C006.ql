[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.114160,105.531494,21.159496,105.579817)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.114160,105.531494,21.159496,105.579817);
  node["barrier"](21.114160,105.531494,21.159496,105.579817);
);
(._; >>;);
out meta;
out count;
