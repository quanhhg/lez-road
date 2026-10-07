[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.293089,105.917750,21.338533,105.966247)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.293089,105.917750,21.338533,105.966247);
  node["barrier"](21.293089,105.917750,21.338533,105.966247);
);
(._; >>;);
out meta;
out count;
