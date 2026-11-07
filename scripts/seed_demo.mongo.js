const d = db.getSiblingDB("norecov_demo");

d.libros.deleteMany({});
d.libros.insertMany([
  {titulo:"Bases de datos NoSQL",autor:"Equipo NORECOV",anio:2026},
  {titulo:"Resiliencia con Docker",autor:"Laboratorio BD2",anio:2026},
  {titulo:"MongoDB y Redis",autor:"NORECOV",anio:2026}
]);

d.eventos.deleteMany({});
d.eventos.insertMany([
  {tipo:"backup",ok:true},
  {tipo:"restore",ok:true}
]);

print(JSON.stringify({
  libros:d.libros.countDocuments({}),
  eventos:d.eventos.countDocuments({})
}));
